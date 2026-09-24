"""Timestamped H/D/A market mathematics; acquisition and wagering are excluded."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from hashlib import sha256
import json
from math import fsum, isfinite
import re
from urllib.parse import urlsplit

from dragonhydra.science.evaluation import Probabilities
from dragonhydra.science.temporal import Availability, TemporalMode, aware_utc
from .continuum import EpistemicType


class DemarginMethod(StrEnum):
    PROPORTIONAL = "PROPORTIONAL"
    POWER = "POWER"


def _identity(kind: str, *keys: str) -> str:
    if any(not isinstance(key, str) or not key.strip() for key in keys):
        raise ValueError("Identity keys must be explicit nonempty text")
    return sha256(json.dumps([kind, *keys], separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class ProviderIdentity:
    provider_key: str
    display_name: str

    def __post_init__(self):
        _identity("provider", self.provider_key)
        if not self.display_name.strip():
            raise ValueError("Provider display name is required")

    @property
    def canonical_id(self):
        return _identity("provider", self.provider_key)


@dataclass(frozen=True, slots=True)
class BookmakerIdentity:
    provider_key: str
    provider_bookmaker_key: str
    display_name: str

    def __post_init__(self):
        _identity("bookmaker", self.provider_key, self.provider_bookmaker_key)
        if not self.display_name.strip():
            raise ValueError("Bookmaker display name is required")

    @property
    def canonical_id(self):
        return _identity("bookmaker", self.provider_key, self.provider_bookmaker_key)


@dataclass(frozen=True, slots=True)
class MarketIdentity:
    provider_key: str
    fixture_id: str
    provider_market_key: str = "HDA_REGULATION"

    def __post_init__(self):
        _identity("market", self.provider_key, self.fixture_id, self.provider_market_key)
        if self.provider_market_key != "HDA_REGULATION":
            raise ValueError("This bounded implementation supports regulation HOME/DRAW/AWAY only")

    @property
    def canonical_id(self):
        return _identity("market", self.provider_key, self.fixture_id, self.provider_market_key)


@dataclass(frozen=True, slots=True)
class DecimalOdds:
    home: float
    draw: float
    away: float

    def __post_init__(self):
        if any(isinstance(value, bool) or not isinstance(value, (int, float))
               or not isfinite(value) or value <= 1 for value in self.values):
            raise ValueError("Decimal odds must be finite and strictly greater than one")

    @property
    def values(self):
        return self.home, self.draw, self.away

    @property
    def implied(self):
        return tuple(1 / value for value in self.values)

    @property
    def overround(self):
        return fsum(self.implied) - 1


def demargin(odds: DecimalOdds, method: DemarginMethod = DemarginMethod.PROPORTIONAL) -> Probabilities:
    if not isinstance(odds, DecimalOdds) or not isinstance(method, DemarginMethod):
        raise ValueError("Typed odds and demargin method are required")
    values = odds.implied
    if method is DemarginMethod.PROPORTIONAL:
        total = fsum(values)
        return Probabilities(*(value / total for value in values))
    # Solve sum(q_i ** k)=1. Positive exponent also supports an underround.
    lower, upper = 0.0, 1.0
    while fsum(value ** upper for value in values) > 1:
        upper *= 2
    for _ in range(120):
        exponent = (lower + upper) / 2
        if fsum(value ** exponent for value in values) > 1:
            lower = exponent
        else:
            upper = exponent
    powers = tuple(value ** ((lower + upper) / 2) for value in values)
    total = fsum(powers)
    return Probabilities(*(value / total for value in powers))


def fair_odds(probabilities: Probabilities) -> tuple[float | None, float | None, float | None]:
    """Zero probability maps to explicit unknown/unbounded price, never JSON Infinity."""
    prices = tuple(1 / value if value else None for value in probabilities.values)
    return tuple(value if value is not None and isfinite(value) else None for value in prices)


@dataclass(frozen=True, slots=True)
class OddsObservation:
    snapshot_id: str
    fixture_id: str
    bookmaker: BookmakerIdentity
    odds: DecimalOdds
    quoted_at: datetime
    kickoff_at: datetime
    availability: Availability
    source_url: str
    parser_version: str
    source_policy_version: str
    evidence_hash: str
    provider: ProviderIdentity
    market: MarketIdentity
    synthetic: bool = False
    closing_evidence: str | None = None

    def __post_init__(self):
        for name in ("snapshot_id", "fixture_id", "parser_version", "source_policy_version"):
            if not isinstance(getattr(self, name), str) or not getattr(self, name).strip():
                raise ValueError(f"{name} is required")
        quoted, kickoff = aware_utc(self.quoted_at), aware_utc(self.kickoff_at)
        if quoted > kickoff:
            raise ValueError("Only pre-match market snapshots are supported")
        if not isinstance(self.odds, DecimalOdds) or not isinstance(self.availability, Availability):
            raise ValueError("Typed odds and availability are required")
        if (not isinstance(self.bookmaker, BookmakerIdentity) or not isinstance(self.provider, ProviderIdentity)
                or not isinstance(self.market, MarketIdentity)):
            raise ValueError("Canonical provider, bookmaker and market identities are required")
        if (self.bookmaker.provider_key != self.provider.provider_key
                or self.market.provider_key != self.provider.provider_key or self.market.fixture_id != self.fixture_id):
            raise ValueError("Provider-scoped bookmaker/market identities must agree with the observation")
        if type(self.synthetic) is not bool:
            raise ValueError("Synthetic label must be explicit")
        if self.availability.available_at is not None and self.availability.available_at < quoted:
            raise ValueError("A quote cannot be available before it exists")
        if quoted > self.availability.observed_at:
            raise ValueError("An observed market capture cannot contain a quote from after its observation")
        url = urlsplit(self.source_url)
        if url.scheme not in ("https", "http") or not url.netloc or url.username or url.password or url.query or url.fragment:
            raise ValueError("Use a public nonsecret source URL without query credentials")
        if re.fullmatch(r"[0-9a-f]{64}", self.evidence_hash) is None:
            raise ValueError("Evidence hash must be SHA-256")
        if self.closing_evidence is not None and not self.closing_evidence.strip():
            raise ValueError("Closing classification requires an explicit proof reference")

    def to_dict(self):
        return {"snapshot_id": self.snapshot_id, "fixture_id": self.fixture_id,
                "bookmaker": {"canonical_id": self.bookmaker.canonical_id,
                              "provider_bookmaker_key": self.bookmaker.provider_bookmaker_key,
                              "display_name": self.bookmaker.display_name},
                "provider": {"canonical_id": self.provider.canonical_id, "provider_key": self.provider.provider_key,
                             "display_name": self.provider.display_name},
                "market": {"canonical_id": self.market.canonical_id, "provider_market_key": self.market.provider_market_key},
                "decimal_odds": list(self.odds.values),
                "quoted_at": self.quoted_at.isoformat(), "kickoff_at": self.kickoff_at.isoformat(),
                "availability": self.availability.to_dict(), "source_url": self.source_url,
                "parser_version": self.parser_version, "source_policy_version": self.source_policy_version,
                "evidence_hash": self.evidence_hash, "synthetic": self.synthetic,
                "closing_evidence": self.closing_evidence,
                "epistemic_type": (EpistemicType.MARKET_OBSERVATION.value
                                   if self.availability.availability_mode is TemporalMode.STRICT_PIT
                                   else EpistemicType.RECONSTRUCTION.value)}


def market_as_of(observations: tuple[OddsObservation, ...], target_as_of: datetime,
                 mode: TemporalMode, *, fixture_id: str) -> tuple[OddsObservation, ...]:
    target = aware_utc(target_as_of)
    if len({row.snapshot_id for row in observations}) != len(observations):
        raise ValueError("Duplicate market snapshot identities are not permitted")
    rows = tuple(row for row in observations if row.fixture_id == fixture_id
                 and row.quoted_at <= target and row.availability.eligible(target, mode))
    if len({row.kickoff_at for row in rows}) > 1:
        raise ValueError("Resolve schedule revisions before comparing market snapshots")
    if len({row.synthetic for row in rows}) > 1:
        raise ValueError("Synthetic and real observations must never be pooled")
    versions = {}
    for row in rows:
        key = (row.market.canonical_id, row.bookmaker.canonical_id,
               row.quoted_at, row.availability.available_at)
        if key in versions and versions[key] != row.odds:
            raise ValueError("Ambiguous market revisions share both quote and availability timestamps")
        versions[key] = row.odds
    return tuple(sorted(rows, key=_quote_order))


def _quote_order(row: OddsObservation):
    return row.quoted_at, row.availability.available_at, row.snapshot_id


def _input_metadata(rows: tuple[OddsObservation, ...] | list[OddsObservation]) -> dict:
    mode = (TemporalMode.RECONSTRUCTED_PIT if any(row.availability.availability_mode is TemporalMode.RECONSTRUCTED_PIT
                                                for row in rows) else TemporalMode.STRICT_PIT)
    return {"temporal_mode": mode.value, "synthetic": any(row.synthetic for row in rows),
            "input_evidence": [{"snapshot_id": row.snapshot_id, "evidence_hash": row.evidence_hash,
                                "availability": row.availability.to_dict(), "synthetic": row.synthetic,
                                "source_url": row.source_url, "parser_version": row.parser_version,
                                "source_policy_version": row.source_policy_version,
                                "provider_id": row.provider.canonical_id, "market_id": row.market.canonical_id,
                                "bookmaker_id": row.bookmaker.canonical_id} for row in rows]}


def _selected(rows: tuple[OddsObservation, ...], target_as_of: datetime, mode: TemporalMode) -> tuple[OddsObservation, ...]:
    if len({row.fixture_id for row in rows}) > 1:
        raise ValueError("Select exactly one fixture per market query")
    return market_as_of(rows, target_as_of, mode, fixture_id=rows[0].fixture_id) if rows else ()


def opening_latest(rows: tuple[OddsObservation, ...], *, target_as_of: datetime,
                   mode: TemporalMode) -> dict[str, dict]:
    """Opening means first retained quote; latest does not imply verified close."""
    rows = _selected(rows, target_as_of, mode)
    result = {}
    for bookmaker in sorted({row.bookmaker.canonical_id for row in rows}):
        history = sorted((row for row in rows if row.bookmaker.canonical_id == bookmaker), key=_quote_order)
        result[bookmaker] = {"first_retained": history[0].snapshot_id, "latest_retained": history[-1].snapshot_id,
                             "verified_closing": history[-1].snapshot_id if history[-1].closing_evidence else None,
                             **_input_metadata(history)}
    return result


def consensus(rows: tuple[OddsObservation, ...], method: DemarginMethod = DemarginMethod.PROPORTIONAL,
              *, target_as_of: datetime, mode: TemporalMode) -> Probabilities | None:
    rows = _selected(rows, target_as_of, mode)
    if not rows:
        return None
    if len({row.fixture_id for row in rows}) != 1 or len({row.synthetic for row in rows}) != 1:
        raise ValueError("Consensus requires one fixture and one evidence class")
    if len({row.provider.canonical_id for row in rows}) != 1:
        raise ValueError("Cross-provider bookmaker consensus requires an explicit crosswalk; never double-count aliases")
    latest = {}
    for row in sorted(rows, key=_quote_order):
        latest[row.bookmaker.canonical_id] = row
    probabilities = tuple(demargin(row.odds, method) for row in latest.values())
    return Probabilities(*(fsum(row.values[index] for row in probabilities) / len(probabilities) for index in range(3)))


def consensus_report(rows: tuple[OddsObservation, ...], method: DemarginMethod = DemarginMethod.PROPORTIONAL,
                     *, target_as_of: datetime, mode: TemporalMode) -> dict:
    """Provenance-preserving export; consensus() alone is the numerical primitive."""
    selected = _selected(rows, target_as_of, mode)
    probabilities = consensus(selected, method, target_as_of=target_as_of, mode=mode)
    return {"epistemic_type": EpistemicType.DERIVED_FEATURE.value,
            "target_as_of": aware_utc(target_as_of).isoformat(), "requested_temporal_mode": TemporalMode(mode).value,
            "method": method.value, "probabilities": probabilities.to_dict() if probabilities is not None else None,
            "state": "CALCULATED" if probabilities is not None else "INSUFFICIENT_EVIDENCE",
            **_input_metadata(selected)}


def trajectory(rows: tuple[OddsObservation, ...], bookmaker: str,
               method: DemarginMethod = DemarginMethod.PROPORTIONAL,
               *, target_as_of: datetime, mode: TemporalMode) -> dict:
    rows = _selected(rows, target_as_of, mode)
    selected = sorted((row for row in rows if row.bookmaker.canonical_id == bookmaker), key=_quote_order)
    if len({row.fixture_id for row in selected}) > 1 or len({row.synthetic for row in selected}) > 1:
        raise ValueError("A trajectory requires one fixture and one evidence class")
    points = [{"snapshot_id": row.snapshot_id, "quoted_at": row.quoted_at.isoformat(),
               "fair_probability": demargin(row.odds, method).to_dict()} for row in selected]
    velocity = None
    # A corrected quote is a revision, not another elapsed market-time sample.
    latest_per_quote = {row.quoted_at: row for row in selected}
    resolved = sorted(latest_per_quote.values(), key=_quote_order)
    if len(resolved) >= 2:
        hours = (resolved[-1].quoted_at - resolved[-2].quoted_at).total_seconds() / 3600
        if hours > 0:
            before, after = (demargin(row.odds, method) for row in resolved[-2:])
            velocity = [(new - old) / hours for old, new in zip(before.values, after.values)]
    return {"bookmaker": bookmaker, "points": points, "probability_change_per_hour": velocity,
            "interpretation": "DESCRIPTIVE_NOT_A_PROFIT_SIGNAL",
            "epistemic_type": EpistemicType.DERIVED_FEATURE.value, **_input_metadata(selected)}


def future_hypothesis(rows: tuple[OddsObservation, ...], bookmaker: str,
                      *, projected_at: datetime, computed_at: datetime) -> dict:
    """Bounded constant-velocity thought experiment; never market evidence."""
    computed, projected = aware_utc(computed_at), aware_utc(projected_at)
    if not computed < projected <= computed + timedelta(hours=24):
        raise ValueError("Projection horizon must be future and no more than 24 hours")
    if any(row.availability.available_at is None or row.availability.available_at > computed
           or row.availability.ingested_at > computed for row in rows):
        raise ValueError("Projection inputs must already be available")
    view = trajectory(rows, bookmaker, target_as_of=computed, mode=TemporalMode.RECONSTRUCTED_PIT)
    selected = [row for row in _selected(rows, computed, TemporalMode.RECONSTRUCTED_PIT)
                if row.bookmaker.canonical_id == bookmaker]
    if not selected or view["probability_change_per_hour"] is None:
        raise ValueError("At least two distinct quote times are needed")
    latest = max(selected, key=_quote_order)
    hours = (projected - latest.quoted_at).total_seconds() / 3600
    raw = [max(0.0, min(1.0, value + velocity * hours)) for value, velocity in
           zip(demargin(latest.odds).values, view["probability_change_per_hour"])]
    total = fsum(raw)
    projected_probabilities = Probabilities(*(value / total for value in raw)) if total else demargin(latest.odds)
    return {"epistemic_type": EpistemicType.HYPOTHESIS.value, "computed_at": computed.isoformat(),
            "projected_at": projected.isoformat(), "probabilities": projected_probabilities.to_dict(),
            "input_snapshot_ids": [row.snapshot_id for row in selected],
            "method": "CLIPPED_RENORMALIZED_CONSTANT_VELOCITY", "validated_forecasting_model": False,
            **_input_metadata(selected)}
