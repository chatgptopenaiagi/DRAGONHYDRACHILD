"""Reviewed source-scoped team aliases; unknown names never mint identities.

The initial UUIDs preserve previously captured CHILD identity keys exactly.
These aliases are local declarations, not provider-issued IDs or global team
reconciliation. Knowledge time is the actual registry review time.
"""

from copy import deepcopy
from dataclasses import replace
from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path
import re

from dragonhydra.config import PROJECT_ROOT
from dragonhydra.science.entities import (
    CrosswalkRecord, EntityRegistry, EntityResolution, EntityType, ResolutionMethod,
    ReviewState, Team, TeamId, normalize_name, team_id,
)
from dragonhydra.science.temporal import aware_utc


REGISTRY_PATH = Path("config/child-entity-crosswalk.json")
PROVIDER = "openfootball"
SCOPE = "openfootball:en.1"
IDENTITY_SCOPE = "DECLARED_SOURCE_SCOPE_NOT_PROVIDER_ISSUED"


def _time(value: str) -> datetime:
    return aware_utc(datetime.fromisoformat(value))


def _hash(value: str):
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ValueError("Source evidence must have a SHA-256 content hash")


def alias_key(alias: str, canonical_id: str) -> str:
    """Include target identity so two same-name candidates remain ambiguous."""
    TeamId(canonical_id)
    normalized_hash = sha256(normalize_name(alias).encode("utf-8")).hexdigest()
    return f"declared-alias:{canonical_id}:{normalized_hash}"


def validate_registry(document: dict) -> EntityRegistry:
    if (document.get("schema_version") != 1 or document.get("provider") != PROVIDER
            or document.get("competition") != "en.1" or document.get("identity_scope") != IDENTITY_SCOPE):
        raise ValueError("Unsupported source-scoped identity registry")
    if type(document.get("registry_version")) is not int or document["registry_version"] < 1:
        raise ValueError("Registry version must be a positive integer")
    created = _time(document["created_at"])
    source = document["source_observation"]
    observed = _time(source["retrieved_at"])
    _hash(source["content_hash"])
    if source["source_id"] != PROVIDER or source["license"] != "CC0-1.0" or observed > created:
        raise ValueError("Registry origin cannot precede genuine source capture")
    if not isinstance(document.get("teams"), list) or not document["teams"] or len(document["teams"]) > 100:
        raise ValueError("Team registry must be a bounded explicit list")
    registry = EntityRegistry()
    seen = set()
    for row in document["teams"]:
        canonical = TeamId(row["canonical_id"])
        if canonical in seen or canonical != team_id(SCOPE, row["founding_declared_key"]):
            raise ValueError("Canonical UUID must preserve the originally declared source key")
        seen.add(canonical)
        registry.register(Team(canonical, row["display_name"]))
    if not isinstance(document.get("crosswalks"), list) or len(document["crosswalks"]) > 1000:
        raise ValueError("Crosswalk records must be a bounded explicit list")
    for row in document["crosswalks"]:
        _hash(row["source_hash"])
        recorded, captured = _time(row["recorded_at"]), _time(row["source_observed_at"])
        if recorded < created or recorded < captured:
            raise ValueError("Alias knowledge cannot be backdated before creation or evidence capture")
        if (row["provider"] != PROVIDER or row["identity_scope"] != IDENTITY_SCOPE
                or row["entity_type"] != "team" or row["resolution_method"] != "DECLARED_ALIAS"
                or not row["review_reason"].strip() or not row["source_policy_version"].strip()):
            raise ValueError("Crosswalk must retain its explicit declared-alias review")
        if row["provider_entity_id"] != alias_key(row["provider_name"], row["canonical_id"]):
            raise ValueError("Declared alias key does not match its canonical identity")
        registry.append_crosswalk(CrosswalkRecord(
            row["provider"], row["provider_entity_id"], row["provider_name"], EntityType.TEAM,
            TeamId(row["canonical_id"]), _time(row["valid_from"]),
            _time(row["valid_to"]) if row["valid_to"] else None, recorded,
            ResolutionMethod.DECLARED_ALIAS, row["confidence"], ReviewState(row["review_state"]), row["revision"]))
    return registry


def load_document(root: Path = PROJECT_ROOT) -> dict:
    document = json.loads((Path(root) / REGISTRY_PATH).read_text(encoding="utf-8"))
    validate_registry(document)
    return document


def load_team_registry(root: Path = PROJECT_ROOT) -> EntityRegistry:
    return validate_registry(load_document(root))


def resolve_in_registry(document: dict, name: str, as_of: datetime) -> EntityResolution:
    instant = aware_utc(as_of)
    result = validate_registry(document).resolve_name(PROVIDER, EntityType.TEAM, name,
                                                     valid_at=instant, known_at=instant)
    # Exact whitespace/case normalization chooses only explicitly reviewed aliases.
    return replace(result, resolution_method=ResolutionMethod.DECLARED_ALIAS) if result.resolved else result


def resolve_team(name: str, as_of: datetime, root: Path = PROJECT_ROOT) -> EntityResolution:
    return resolve_in_registry(load_document(root), name, as_of)


def append_declared_alias(document: dict, *, alias: str, canonical_id: str,
                          recorded_at: datetime, source_observed_at: datetime,
                          source_hash: str, source_policy_version: str, review_reason: str,
                          confidence: float = 0.8, review_state: ReviewState = ReviewState.CONFIRMED,
                          valid_from: datetime | None = None) -> dict:
    """Return a new reviewed registry revision; never mutate/write old history.

    A renamed source team needs this explicit alias declaration referencing its
    existing UUID. The function cannot infer that two similar names mean one team.
    """
    original = validate_registry(document)
    identifier = TeamId(canonical_id)
    if identifier not in {team.canonical_id for team in original.entities}:
        raise ValueError("Alias references an unknown canonical team")
    recorded, captured = aware_utc(recorded_at), aware_utc(source_observed_at)
    if any(recorded < _time(row["recorded_at"]) for row in document["crosswalks"]):
        raise ValueError("New registry revision knowledge cannot precede existing reviews")
    revised = deepcopy(document)
    key = alias_key(alias, canonical_id)
    history = [row for row in revised["crosswalks"] if row["provider_entity_id"] == key]
    revised["registry_version"] += 1
    revised["crosswalks"].append({
        "provider": PROVIDER, "provider_entity_id": key, "provider_name": alias,
        "entity_type": "team", "canonical_id": canonical_id, "identity_scope": IDENTITY_SCOPE,
        "valid_from": aware_utc(valid_from or recorded).isoformat(), "valid_to": None,
        "recorded_at": recorded.isoformat(), "resolution_method": "DECLARED_ALIAS",
        "confidence": confidence, "review_state": review_state.value, "revision": len(history) + 1,
        "source_observed_at": captured.isoformat(), "source_hash": source_hash,
        "source_policy_version": source_policy_version, "review_reason": review_reason,
    })
    validate_registry(revised)
    return revised


def registry_records(root: Path = PROJECT_ROOT) -> tuple[dict, ...]:
    """Small JSON-ready entity projections for CHILD SQL append integration."""
    document = load_document(root)
    records = []
    for team in document["teams"]:
        mappings = [row for row in document["crosswalks"] if row["canonical_id"] == team["canonical_id"]]
        records.append({"entity_type": "team", **team, "provider": PROVIDER,
                        "identity_scope": IDENTITY_SCOPE, "registry_version": document["registry_version"],
                        "recorded_at": max((_time(row["recorded_at"]) for row in mappings), default=_time(document["created_at"])).isoformat(),
                        "source_observation": document["source_observation"], "crosswalks": mappings})
    return tuple(records)
