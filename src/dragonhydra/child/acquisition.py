"""One-league bounded acquisition, source history and deterministic Medusa gates."""
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path
import re
import time
from uuid import UUID, uuid4

from ..config import PROJECT_ROOT
from ..science.entities import competition_id, fixture_id, EntityType
from .identity import load_team_registry, PROVIDER
from ..science.prospective import RawEvidenceStore, ProspectiveSnapshot, validate_fixture_document
from ..web.contracts import FetchPolicy, PipelineError, public_url, timestamp, utcnow
from ..web.fetch import fetch
from ..web.provenance import digest, encode, exclusive_json
from ..web.terms import allow_source, load_sources


@dataclass(frozen=True)
class SourceAdapter:
    source_id: str
    supported_classes: tuple[str, ...]
    allowed_domains: tuple[str, ...]
    parser_version: str
    timestamp_quality: str
    minimum_interval_seconds: int = 60
    maximum_daily_requests: int = 4


OPENFOOTBALL = SourceAdapter('openfootball', ('fixture', 'team', 'result'),
    ('raw.githubusercontent.com',), 'child-openfootball/1.1',
    'GENUINE_CAPTURE; PROVIDER_PUBLICATION_AND_KICKOFF_TIMEZONE_UNKNOWN')


def normalize(body: bytes, snapshot: dict, *, root=PROJECT_ROOT) -> list[dict]:
    """Source identity is declared/scoped; UTC kickoff is deliberately not inferred."""
    document = json.loads(body)
    validate_fixture_document(body, 'English Premier League 2026/27')
    competition = competition_id('openfootball', 'en.1')
    cursor=datetime.now(timezone.utc)
    registry=load_team_registry(root)
    resolved={}
    for name in {item[key] for item in document['matches'] for key in ('team1','team2')}:
        resolution=registry.resolve_name(PROVIDER,EntityType.TEAM,name,valid_at=cursor,known_at=cursor)
        if not resolution.resolved:
            raise PipelineError('ENTITY_UNRESOLVED')
        resolved[name]=resolution
    rows = []
    for item in document['matches']:
        home = resolved[item['team1']].canonical_id
        away = resolved[item['team2']].canonical_id
        key = json.dumps([item['round'], str(home), str(away)], ensure_ascii=False, separators=(',', ':'))
        score = item.get('score')
        score_state = 'NOT_REPORTED' if score is None else 'UNKNOWN_FORMAT'
        if isinstance(score, list) and len(score) == 2 and all(type(v) is int and 0 <= v <= 50 for v in score):
            # Bare score arrays lack the explicit ft label. Preserve but do not
            # silently interpret placeholders/live scores as final results.
            score_state = 'UNKNOWN_FORMAT'
        elif score is not None and not isinstance(score, dict):
            raise PipelineError('SCHEMA_CHANGED')
        goals = score.get('ft') if isinstance(score, dict) else None
        if goals is not None and (not isinstance(goals, list) or len(goals) != 2
                or any(type(value) is not int or not 0 <= value <= 50 for value in goals)):
            raise PipelineError('SCHEMA_CHANGED')
        if goals is not None:
            score_state = 'PARSED_FULL_TIME'
        rows.append({'fixture_id': str(fixture_id('openfootball', competition, '2026-27', key)),
            'competition_id': str(competition), 'season': '2026-27', 'round': item['round'],
            'home_team_id': str(home), 'away_team_id': str(away),
            'home_team': item['team1'], 'away_team': item['team2'], 'match_date': item['date'],
            'kickoff_local': item.get('time'), 'kickoff_utc': None,
            'timestamp_quality': 'SOURCE_LOCAL_TIMEZONE_UNVERIFIED',
            'identity_method': 'REVIEWED_DECLARED_ALIAS_AND_ROUND_CANONICAL_TEAM_KEY',
            'identity_resolved_at':cursor.isoformat(),
            'identity_mapping_recorded_at':max(row.recorded_at for key in ('team1','team2') for row in resolved[item[key]].mappings).isoformat(),
            'home_score': goals[0] if goals else None, 'away_score': goals[1] if goals else None,
            'source_score': score, 'score_state': score_state,
            'status': 'REPORTED_FINAL' if goals else 'SCHEDULED',
            'snapshot_id': snapshot['snapshot_id'], 'source_id': snapshot['source_id'],
            'source_url': snapshot['source_url'], 'observed_at': snapshot['observed_at'],
            'retrieved_at': snapshot['retrieved_at'], 'available_at': max(cursor,timestamp(snapshot['available_at'])).isoformat(),
            'content_hash': snapshot['content_hash'], 'parser_version': OPENFOOTBALL.parser_version,
            'source_policy_version': snapshot['source_policy_version'], 'temporal_mode': 'STRICT_PIT',
            'epistemic_state': 'OBSERVATION', 'confidence': 0.8, 'synthetic': False})
    if len({row['fixture_id'] for row in rows}) != len(rows):
        raise PipelineError('ENTITY_UNRESOLVED')
    return rows


def validate_records(records: list[dict], *, at: datetime, seen: dict | None = None) -> dict:
    """Deterministic gates only; no source reputation or entity guessing."""
    known = dict(seen or {})
    decisions = []
    for row in records:
        reasons = []
        required = ('fixture_id', 'home_team_id', 'away_team_id', 'source_id', 'source_url',
                    'observed_at', 'retrieved_at', 'available_at', 'content_hash', 'parser_version')
        if any(not row.get(key) for key in required):
            reasons.append('MISSING_PROVENANCE')
        try:
            public_url(row['source_url'])
            if not re.fullmatch('[a-f0-9]{64}', row['content_hash']):
                raise ValueError()
        except (KeyError, TypeError, ValueError):
            reasons.append('SCHEMA_CHANGED')
        try:
            if not timestamp(row['observed_at']) <= timestamp(row['retrieved_at']) <= timestamp(row['available_at']) <= at:
                reasons.append('FUTURE_TIMESTAMP')
            if at - timestamp(row['retrieved_at']) > timedelta(days=7):
                reasons.append('STALE_DATA')
        except (KeyError, ValueError, TypeError):
            reasons.append('SCHEMA_CHANGED')
        try:
            for field in ('fixture_id', 'home_team_id', 'away_team_id'):
                UUID(row[field])
        except (KeyError, TypeError, ValueError, AttributeError):
            reasons.append('ENTITY_UNRESOLVED')
        if row.get('home_team_id') == row.get('away_team_id'):
            reasons.append('ENTITY_UNRESOLVED')
        if row.get('temporal_mode') != 'STRICT_PIT' or row.get('epistemic_state') != 'OBSERVATION':
            reasons.append('EPISTEMIC_STATE_INVALID')
        identifier = row.get('fixture_id', '')
        body_hash = digest(encode(row))
        if identifier in known:
            reasons.append('DUPLICATE' if known[identifier] == body_hash else 'CONFLICTING_DATA')
        known[identifier] = body_hash
        verdict = 'ACCEPT' if not reasons else ('QUARANTINE' if set(reasons) <= {'STALE_DATA', 'CONFLICTING_DATA'} else 'REJECT')
        decisions.append({'fixture_id': identifier, 'verdict': verdict, 'reason_codes': sorted(set(reasons))})
    return {'decisions': decisions, 'accepted': sum(row['verdict'] == 'ACCEPT' for row in decisions),
            'quarantined': sum(row['verdict'] == 'QUARANTINE' for row in decisions),
            'rejected': sum(row['verdict'] == 'REJECT' for row in decisions)}


def collect_once(*, root: Path = PROJECT_ROOT, persist: bool = True) -> dict:
    """No auto retry, max four attempts/day, one source and one file per attempt.

    The 60-second lower bound permits two commissioning captures; Windows daily
    scheduling is the normal cadence. Repeated calls cannot bypass the ceiling.
    """
    ledger = root / 'runtime/child/acquisition'
    ledger.mkdir(parents=True, exist_ok=True)
    lock = ledger / '.lock'
    try:
        handle = lock.open('x', encoding='utf-8')
    except FileExistsError:
        return {'status': 'BLOCKED', 'reason': 'COLLECTOR_LOCKED'}
    try:
        with handle:
            handle.write(utcnow())
        now = datetime.now(timezone.utc)
        previous = [json.loads(p.read_text(encoding='utf-8')) for p in ledger.glob('*.json')]
        recent = [p for p in previous if timestamp(p['attempted_at']) > now - timedelta(days=1)]
        if len(recent) >= OPENFOOTBALL.maximum_daily_requests:
            return {'status': 'NOT_DUE', 'reason': 'DAILY_REQUEST_CEILING'}
        if previous and now - max(timestamp(p['attempted_at']) for p in previous) < timedelta(seconds=OPENFOOTBALL.minimum_interval_seconds):
            return {'status': 'NOT_DUE', 'reason': 'MINIMUM_INTERVAL'}
        start = time.perf_counter()
        receipt = {'attempt_id': uuid4().hex, 'attempted_at': now.isoformat(), 'source_id': 'openfootball',
                   'status': 'BLOCKED', 'data_classes': list(OPENFOOTBALL.supported_classes)}
        try:
            source = load_sources(root)['openfootball']
            current = source['prospective']
            allow_source(source, current['url'])
            body, acquisition = fetch(FetchPolicy('openfootball', current['url'], 'CHILD one-league prospective fixture research'), source)
            raw_hash = RawEvidenceStore(root / 'runtime/child/raw').put(body)
            receipt.update(acquisition=acquisition, raw_artifact_hash=raw_hash)
            count = validate_fixture_document(body, current['document_name'])
            snapshot = asdict(ProspectiveSnapshot(uuid4().hex, 'openfootball', current['url'],
                acquisition['retrieved_at'], acquisition['retrieved_at'], utcnow(), raw_hash, raw_hash,
                len(body), acquisition['content_type'], OPENFOOTBALL.parser_version,
                source['policy_version'], digest(encode(source)), current['competition'], current['season'], count))
            snapshot.update(terms_status=source['terms_status'], license_status=source['license_status'],
                            robots_state=acquisition['robots']['robots_status'], confidence=0.8,
                            validation_verdict='ACCEPT', producer='CHILD_BOUNDED_PYTHON_FETCH')
            policy_artifact = root / 'runtime/child/policies' / (snapshot['source_policy_hash'] + '.json')
            if not policy_artifact.exists():
                exclusive_json(policy_artifact, source)
            if digest(encode(json.loads(policy_artifact.read_text(encoding='utf-8')))) != snapshot['source_policy_hash']:
                raise PipelineError('SOURCE_POLICY_HASH_MISMATCH')
            fixtures = normalize(body, snapshot, root=root)
            validation = validate_records(fixtures, at=datetime.now(timezone.utc))
            receipt['medusa'] = validation
            if validation['accepted'] != len(fixtures):
                raise PipelineError('MEDUSA_REJECTED')
            exclusive_json(root / 'runtime/child/snapshots' / (snapshot['snapshot_id'] + '.json'),
                           {'snapshot': snapshot, 'fixtures': fixtures})
            receipt.update(snapshot=snapshot, medusa=validation,
                           acquisition_status='COMPLETE', status='COMPLETE', storage_status='NOT_REQUESTED')
            if persist:
                from .storage import ChildStore, ChildPresentation
                store = ChildStore()
                receipt['storage'] = store.persist_snapshot(snapshot, fixtures)
                summary = store.summary()
                ChildPresentation().cache(summary)
                receipt['storage_status'] = 'COMPLETE'
        except Exception as error:
            receipt.update(status='BLOCKED', reason=str(error) if isinstance(error, PipelineError) else type(error).__name__)
            if receipt.get('acquisition_status') == 'COMPLETE':
                receipt['storage_status'] = 'DATABASE_FAILURE'
        receipt['elapsed_seconds'] = time.perf_counter() - start
        receipt['finished_at'] = utcnow()
        exclusive_json(ledger / (receipt['attempt_id'] + '.json'), receipt)
        return receipt
    finally:
        lock.unlink()


def source_metrics(root: Path = PROJECT_ROOT) -> dict:
    paths = sorted((root / 'runtime/child/acquisition').glob('*.json'))
    rows = sorted((json.loads(p.read_text(encoding='utf-8')) for p in paths), key=lambda row: row['attempted_at'])
    successes = [p for p in rows if p.get('acquisition_status') == 'COMPLETE']
    hashes = [p['raw_artifact_hash'] for p in successes]
    return {'source_id': 'openfootball', 'attempts': len(rows), 'successful_acquisitions': len(successes),
            'validated_acquisition_rate': len(successes) / len(rows) if rows else None,
            'transport_availability_rate': sum('acquisition' in p for p in rows) / len(rows) if rows else None,
            'local_parser_gate_failures': sum(p.get('reason') in ('AttributeError', 'MEDUSA_REJECTED') for p in rows),
            'mean_latency_seconds': sum(p['elapsed_seconds'] for p in rows) / len(rows) if rows else None,
            'observed_content_revisions': sum(a != b for a, b in zip(hashes, hashes[1:])),
            'provider_timestamp_quality': 'UNKNOWN', 'authority': 'COMMUNITY_DATASET',
            'terms_compatibility': 'REVIEWED_CC0', 'long_term_reliability': 'INSUFFICIENT_HISTORY',
            'correction_accuracy': None, 'entity_resolution_accuracy': None}


def fault_injection_report() -> dict:
    """Small labelled controlled challenge set, not a population accuracy claim."""
    from copy import deepcopy
    now = datetime.now(timezone.utc)
    stamp = (now - timedelta(minutes=1)).isoformat()
    base = {'fixture_id': str(uuid4()), 'home_team_id': str(uuid4()), 'away_team_id': str(uuid4()),
            'source_id': 'synthetic-control', 'source_url': 'https://example.org/synthetic',
            'observed_at': stamp, 'retrieved_at': stamp, 'available_at': stamp,
            'content_hash': 'a' * 64, 'parser_version': 'fault-control/1',
            'temporal_mode': 'STRICT_PIT', 'epistemic_state': 'OBSERVATION', 'synthetic': True}
    cases = []
    mutations = {
        'wrong_entity': ({'away_team_id': base['home_team_id']}, 'ENTITY_UNRESOLVED'),
        'future_timestamp': ({'available_at': (now + timedelta(days=1)).isoformat()}, 'FUTURE_TIMESTAMP'),
        'stale_record': ({key: (now - timedelta(days=8)).isoformat() for key in ('observed_at','retrieved_at','available_at')}, 'STALE_DATA'),
        'schema_mutation': ({'available_at': 'not-a-time'}, 'SCHEMA_CHANGED'),
        'missing_provenance': ({'source_id': ''}, 'MISSING_PROVENANCE'),
    }
    for name, (change, expected) in mutations.items():
        row = {**deepcopy(base), **change}
        result = validate_records([row], at=now)['decisions'][0]
        cases.append({'case': name, 'detected': expected in result['reason_codes'], **result})
    for name, row, expected in [('duplicate', base, 'DUPLICATE'),
                              ('conflicting_observation', {**base, 'content_hash': 'b' * 64}, 'CONFLICTING_DATA')]:
        result = validate_records([row], at=now, seen={base['fixture_id']: digest(encode(base))})['decisions'][0]
        cases.append({'case': name, 'detected': expected in result['reason_codes'], **result})
    control = validate_records([base], at=now)['accepted'] == 1
    return {'label': 'SYNTHETIC_CONTROLLED_FAULT_INJECTION', 'faults': len(cases),
            'detected': sum(row['detected'] for row in cases), 'valid_controls': 1,
            'false_positives': int(not control), 'cases': cases,
            'limitation': 'Seven engineered faults do not estimate real-world catch rate.'}
