"""Synthetic known-answer contracts, never a real-market performance claim."""

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from dragonhydra.science.evaluation import Outcome, Probabilities
from dragonhydra.science.temporal import Availability, TemporalMode
from dragonhydra.child.continuum import ContinuumRecord, EpistemicType, cursor
from dragonhydra.child.odds import (BookmakerIdentity, ProviderIdentity, MarketIdentity,
                                    DecimalOdds, DemarginMethod, OddsObservation, consensus, consensus_report,
                                    demargin, fair_odds, future_hypothesis, market_as_of,
                                    opening_latest, trajectory)
from dragonhydra.child.registry import Maturity, OperationalStatus, default_heads, update_head
from dragonhydra.child.uncertainty import (ResearchAnswer, ResearchNeed, ResearchScenario,
                                           entropy, rank_research, run_controlled_research)
from dragonhydra.child.ledger import LedgerProposal, PredictionLedger


ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 9, 24, 12, tzinfo=timezone.utc)
HASH = "a" * 64


def available(at=NOW, mode=TemporalMode.STRICT_PIT):
    return Availability(mode, at, at, at, at, "SYNTHETIC_TEST", "1", "Synthetic contract evidence", 1, "synthetic")


def market(name="one", hours=-2, bookmaker="synthetic-book", odds=(2, 3, 4)):
    quoted = NOW + timedelta(hours=hours)
    return OddsObservation(name, "fixture", BookmakerIdentity("synthetic", bookmaker, bookmaker), DecimalOdds(*odds), quoted, NOW + timedelta(hours=3),
                           available(quoted), "https://example.com/synthetic", "1", "synthetic-policy-1", HASH,
                           ProviderIdentity("synthetic", "Synthetic Provider"), MarketIdentity("synthetic", "fixture"), True)


def need(name="keeper", source="synthetic", deadline=None, cost=0):
    scenarios = (ResearchScenario("available", 0.5, Probabilities(0.7, 0.2, 0.1)),
                 ResearchScenario("absent", 0.5, Probabilities(0.3, 0.3, 0.4)))
    return ResearchNeed(name, "fixture", "keeper", "Is keeper available?", "keeper", (source,), "1",
                        deadline or NOW + timedelta(hours=1), cost, 5, scenarios)


class ChildOddsTests(unittest.TestCase):
    def test_decimal_validation_overround_and_proportional_known_answer(self):
        odds = DecimalOdds(2, 3, 4)
        self.assertAlmostEqual(odds.overround, 1 / 12)
        fair = demargin(odds)
        for actual, expected in zip(fair.values, (6 / 13, 4 / 13, 3 / 13)):
            self.assertAlmostEqual(actual, expected)
        for value in (1, -2, float("nan"), float("inf"), True):
            with self.subTest(value=value), self.assertRaises(ValueError):
                DecimalOdds(value, 3, 4)

    def test_power_normalizes_overround_underround_and_fair_markets(self):
        for odds in (DecimalOdds(2, 3, 4), DecimalOdds(4, 5, 6), DecimalOdds(3, 3, 3)):
            result = demargin(odds, DemarginMethod.POWER)
            self.assertAlmostEqual(sum(result.values), 1)
            self.assertTrue(all(0 <= value <= 1 for value in result.values))
        for value in demargin(DecimalOdds(3, 3, 3), DemarginMethod.POWER).values:
            self.assertAlmostEqual(value, 1 / 3)
        self.assertNotEqual(demargin(DecimalOdds(2, 3, 4), DemarginMethod.POWER), demargin(DecimalOdds(2, 3, 4)))

    def test_fair_odds_zero_and_timestamp_validation(self):
        self.assertEqual(fair_odds(Probabilities(0.5, 0.5, 0)), (2, 2, None))
        with self.assertRaises(ValueError):
            replace(market(), quoted_at=NOW + timedelta(days=1))
        with self.assertRaises(ValueError):
            replace(market(), source_url="https://example.com?api_key=forbidden")

    def test_asof_leakage_canary_and_closing_not_assumed(self):
        opening, later, future = market(), market("later", -1), market("future", 1)
        selected = market_as_of((future, later, opening), NOW, TemporalMode.STRICT_PIT, fixture_id="fixture")
        self.assertEqual(selected, (opening, later))
        self.assertIsNone(opening_latest(selected, target_as_of=NOW, mode=TemporalMode.STRICT_PIT)[opening.bookmaker.canonical_id]["verified_closing"])
        delayed = replace(later, availability=available(NOW + timedelta(hours=1)))
        self.assertEqual(market_as_of((opening, delayed), NOW, TemporalMode.STRICT_PIT, fixture_id="fixture"), (opening,))

    def test_reconstructed_and_synthetic_market_boundaries(self):
        reconstructed = replace(market(), availability=available(NOW - timedelta(hours=2), TemporalMode.RECONSTRUCTED_PIT))
        self.assertEqual(market_as_of((reconstructed,), NOW, TemporalMode.STRICT_PIT, fixture_id="fixture"), ())
        self.assertEqual(reconstructed.to_dict()["epistemic_type"], "RECONSTRUCTION")
        with self.assertRaises(ValueError):
            market_as_of((market(), replace(market("real"), synthetic=False)), NOW, TemporalMode.STRICT_PIT, fixture_id="fixture")

    def test_consensus_uses_one_latest_quote_per_bookmaker(self):
        old, latest, other = market(), market("latest", -1, odds=(3, 3, 3)), market("other", -1, "other", (3, 3, 3))
        self.assertEqual(consensus((old, latest, other), target_as_of=NOW, mode=TemporalMode.STRICT_PIT), Probabilities(1 / 3, 1 / 3, 1 / 3))
        self.assertIsNone(consensus((), target_as_of=NOW, mode=TemporalMode.STRICT_PIT))
        future = market("future", 1, odds=(1.1, 20, 30))
        self.assertEqual(consensus((old, latest, other, future), target_as_of=NOW, mode=TemporalMode.STRICT_PIT), Probabilities(1 / 3, 1 / 3, 1 / 3))

    def test_trajectory_and_hypothesis_never_claim_future_observation(self):
        rows = (market(), market("later", -1, odds=(1.8, 3.4, 4.5)))
        bookmaker = rows[0].bookmaker.canonical_id
        path = trajectory(rows, bookmaker, target_as_of=NOW, mode=TemporalMode.STRICT_PIT)
        self.assertGreater(path["probability_change_per_hour"][0], 0)
        projected = future_hypothesis(rows, bookmaker, projected_at=NOW + timedelta(hours=1), computed_at=NOW)
        self.assertEqual(projected["epistemic_type"], "HYPOTHESIS")
        self.assertFalse(projected["validated_forecasting_model"])
        self.assertAlmostEqual(sum(projected["probabilities"].values()), 1)
        with self.assertRaises(ValueError):
            future_hypothesis(rows, bookmaker, projected_at=NOW - timedelta(hours=1), computed_at=NOW)

    def test_provider_market_bookmaker_identity_is_independent_of_display_names(self):
        row = market()
        renamed = replace(row.bookmaker, display_name="Renamed bookmaker")
        self.assertEqual(renamed.canonical_id, row.bookmaker.canonical_id)
        self.assertNotEqual(replace(row.bookmaker, provider_key="another-provider").canonical_id, row.bookmaker.canonical_id)
        self.assertEqual(replace(row.provider, display_name="Renamed provider").canonical_id, row.provider.canonical_id)
        with self.assertRaises(ValueError):
            replace(row, market=MarketIdentity("synthetic", "wrong-fixture"))
        with self.assertRaises(ValueError):
            replace(row, bookmaker=replace(row.bookmaker, provider_key="different"))

    def test_equal_quote_revisions_use_availability_not_lexical_snapshot_id(self):
        initial = market("z-old", -2)
        corrected = replace(market("a-corrected", -2, odds=(3, 3, 3)), availability=available(NOW - timedelta(hours=1)))
        earlier = market("previous-quote", -3, odds=(4, 3, 2))
        rows = (corrected, earlier, initial)
        bookmaker = initial.bookmaker.canonical_id
        self.assertEqual(opening_latest(rows, target_as_of=NOW, mode=TemporalMode.STRICT_PIT)[bookmaker]["latest_retained"], corrected.snapshot_id)
        self.assertEqual(consensus(rows, target_as_of=NOW, mode=TemporalMode.STRICT_PIT), demargin(corrected.odds))
        earlier_cursor = NOW - timedelta(hours=1, minutes=30)
        self.assertEqual(consensus(rows, target_as_of=earlier_cursor, mode=TemporalMode.STRICT_PIT), demargin(initial.odds))
        path = trajectory(rows, bookmaker, target_as_of=NOW, mode=TemporalMode.STRICT_PIT)
        self.assertEqual(path["points"][-1]["snapshot_id"], corrected.snapshot_id)
        expected_velocity = [later - before for before, later in zip(demargin(earlier.odds).values, demargin(corrected.odds).values)]
        self.assertEqual(path["probability_change_per_hour"], expected_velocity)
        with self.assertRaises(ValueError):
            consensus((initial, replace(corrected, availability=initial.availability)), target_as_of=NOW, mode=TemporalMode.STRICT_PIT)

    def test_reconstructed_assumptions_survive_market_projection(self):
        rows = tuple(replace(row, availability=replace(row.availability, availability_mode=TemporalMode.RECONSTRUCTED_PIT,
                                                       availability_policy="DECLARED_HISTORICAL_QUOTE_POLICY",
                                                       assumption_reason="Synthetic reconstruction test"))
                     for row in (market(), market("later", -1, odds=(1.8, 3.4, 4.5))))
        bookmaker = rows[0].bookmaker.canonical_id
        result = future_hypothesis(rows, bookmaker, projected_at=NOW + timedelta(hours=1), computed_at=NOW)
        self.assertEqual(result["epistemic_type"], "HYPOTHESIS")
        self.assertEqual(result["temporal_mode"], "RECONSTRUCTED_PIT")
        self.assertTrue(result["synthetic"])
        for source, retained in zip(rows, result["input_evidence"]):
            self.assertEqual(retained["availability"], source.availability.to_dict())
            self.assertEqual(retained["evidence_hash"], source.evidence_hash)
        path = trajectory(rows, bookmaker, target_as_of=NOW, mode=TemporalMode.RECONSTRUCTED_PIT)
        self.assertEqual(path["temporal_mode"], "RECONSTRUCTED_PIT")
        exported = consensus_report(rows, target_as_of=NOW, mode=TemporalMode.RECONSTRUCTED_PIT)
        self.assertEqual(exported["temporal_mode"], "RECONSTRUCTED_PIT")
        self.assertEqual(exported["input_evidence"][0]["availability"], rows[0].availability.to_dict())

    def test_quote_cannot_postdate_the_capture_observation(self):
        row = market()
        lagged_ingestion = replace(row.availability, available_at=NOW, retrieved_at=NOW, ingested_at=NOW)
        with self.assertRaises(ValueError):
            replace(row, quoted_at=NOW - timedelta(hours=1), availability=lagged_ingestion)


class ChildUncertaintyTests(unittest.TestCase):
    def test_entropy_extremes_and_policy_cost_deadline_ranking(self):
        self.assertEqual(entropy(Probabilities(1, 0, 0)), 0)
        baseline = Probabilities(0.5, 0.25, 0.25)
        requests = (need("approved"), need("blocked", "blocked"), need("expensive", cost=10),
                    need("expired", deadline=NOW - timedelta(seconds=1)))
        ranked = rank_research(requests, baseline, {"synthetic": "APPROVED"}, now=NOW, cost_budget=1)
        self.assertEqual(ranked[0]["need_id"], "approved")
        self.assertTrue(ranked[0]["feasible"])
        self.assertTrue(all(not item["feasible"] for item in ranked[1:]))

    def test_controlled_research_validates_before_recalculation_and_measures(self):
        trace = []
        answer = ResearchAnswer("answer", "synthetic", "keeper", "available", available(), HASH, True)

        def fetch(request, source):
            trace.append("fetch")
            return answer

        def validate(row):
            trace.append("validate")
            return row.content_hash == HASH

        def recalculate(row):
            trace.append("recalculate")
            return Probabilities(0.7, 0.2, 0.1)

        result = run_controlled_research(need(), Probabilities(0.5, 0.25, 0.25), {"synthetic": "APPROVED"},
                                        now=NOW, known_fields=frozenset({"fixture"}), required_fields=frozenset({"fixture", "keeper"}),
                                        fetcher=fetch, validator=validate, recalculator=recalculate, cost_budget=0)
        self.assertEqual(trace, ["fetch", "validate", "recalculate"])
        self.assertEqual(result["state"], "VALIDATED_RECALCULATED")
        self.assertGreater(result["entropy_reduction"], 0)
        self.assertEqual((result["completeness_before"], result["completeness_after"]), (0.5, 1))
        self.assertTrue(result["synthetic"])
        self.assertFalse(result["real_world_benefit_proven"])

    def test_blocked_policy_prevents_fetch_and_failed_validation_prevents_recalc(self):
        kwargs = dict(now=NOW, known_fields=frozenset(), required_fields=frozenset({"keeper"}), cost_budget=0)
        forbidden = lambda *args: self.fail("Callback must not be invoked")
        blocked = run_controlled_research(need(), Probabilities(1 / 3, 1 / 3, 1 / 3), {},
                                         fetcher=forbidden, validator=forbidden, recalculator=forbidden, **kwargs)
        self.assertEqual(blocked["state"], "TERMS_BLOCKED")
        answer = ResearchAnswer("answer", "synthetic", "keeper", True, available(), HASH, True)
        rejected = run_controlled_research(need(), Probabilities(1 / 3, 1 / 3, 1 / 3), {"synthetic": "APPROVED"},
                                          fetcher=lambda *args: answer, validator=lambda row: False, recalculator=forbidden, **kwargs)
        self.assertEqual(rejected["state"], "QUARANTINE")
        with self.assertRaises(ValueError):
            replace(answer, source_id="undeclared")

        def unavailable(*args):
            raise RuntimeError("Synthetic private error detail must not be exposed")

        failed = run_controlled_research(need(), Probabilities(1 / 3, 1 / 3, 1 / 3), {"synthetic": "APPROVED"},
                                        fetcher=unavailable, validator=forbidden, recalculator=forbidden, **kwargs)
        self.assertEqual(failed["state"], "SOURCE_UNAVAILABLE")
        self.assertNotIn("private error detail", json.dumps(failed))

    def test_future_answer_rejected_and_negative_entropy_gain_retained(self):
        kwargs = dict(now=NOW, known_fields=frozenset(), required_fields=frozenset({"keeper"}), cost_budget=0)
        answer = ResearchAnswer("answer", "synthetic", "keeper", True, available(NOW + timedelta(seconds=1)), HASH, True)
        result = run_controlled_research(need(), Probabilities(0.9, 0.05, 0.05), {"synthetic": "APPROVED"},
                                        fetcher=lambda *args: answer, validator=lambda row: True,
                                        recalculator=lambda row: Probabilities(1 / 3, 1 / 3, 1 / 3), **kwargs)
        self.assertEqual(result["state"], "REJECT")
        answer = replace(answer, availability=available())
        result = run_controlled_research(need(), Probabilities(0.9, 0.05, 0.05), {"synthetic": "APPROVED"},
                                        fetcher=lambda *args: answer, validator=lambda row: True,
                                        recalculator=lambda row: Probabilities(1 / 3, 1 / 3, 1 / 3), **kwargs)
        self.assertLess(result["entropy_reduction"], 0)


class ChildContinuumRegistryTests(unittest.TestCase):
    def test_cursor_preserves_epistemic_type_and_excludes_future_knowledge(self):
        observed = ContinuumRecord("observed", "fixture", EpistemicType.OBSERVATION,
                                   NOW + timedelta(days=1), available(), ("raw",), "Future schedule known now")
        hypothesis = replace(observed, record_id="hypothesis", epistemic_type=EpistemicType.HYPOTHESIS)
        later = replace(observed, record_id="later", availability=available(NOW + timedelta(seconds=1)))
        self.assertEqual(len(cursor((observed, hypothesis, later), NOW, TemporalMode.STRICT_PIT)), 2)
        self.assertEqual(cursor((observed, hypothesis, later), NOW, TemporalMode.STRICT_PIT, observed_facts_only=True), (observed,))
        with self.assertRaises(ValueError):
            hypothesis.require_observed_fact()
        with self.assertRaises(ValueError):
            replace(observed, synthetic=True).require_observed_fact()

    def test_reconstruction_cannot_be_labeled_observation(self):
        with self.assertRaises(ValueError):
            ContinuumRecord("r", "f", EpistemicType.OBSERVATION, NOW,
                            available(NOW, TemporalMode.RECONSTRUCTED_PIT), ("raw",), "reconstructed")

    def test_registry_is_thirteen_logical_heads_and_no_false_operational_claim(self):
        heads = default_heads()
        self.assertEqual(len(heads), 13)
        self.assertTrue(all(item.operational_status is OperationalStatus.NOT_STARTED for item in heads if item.head != "PLAYER"))
        self.assertEqual(next(item for item in heads if item.head == "PLAYER").operational_status, OperationalStatus.SOURCE_UNAVAILABLE)
        self.assertTrue(all(item.reliability_score is None for item in heads))
        with self.assertRaises(ValueError):
            update_head(heads, "MATCH", operational_status=OperationalStatus.ACTIVE)
        with self.assertRaises(ValueError):
            update_head(heads, "MATCH", maturity=Maturity.VALIDATED)
        ready = update_head(heads, "MATCH", allowed_sources=("synthetic",), maturity=Maturity.EXPERIMENTAL,
                            operational_status=OperationalStatus.READY)
        self.assertEqual(ready[0].to_dict()["execution_model"], "LOGICAL_CAPABILITY_SHARED_FETCHER")


class ChildLedgerTests(unittest.TestCase):
    def setUp(self):
        (ROOT / "runtime/tmp").mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=ROOT / "runtime/tmp")
        self.addCleanup(self.temp.cleanup)
        self.ledger = PredictionLedger(Path(self.temp.name))
        self.proposal = LedgerProposal("fixture", NOW + timedelta(hours=1), Probabilities(0.5, 0.3, 0.2),
                                       "synthetic-model", "1", HASH, HASH, ("synthetic",), HASH, (available(),), True)

    def test_prospective_actual_clock_hashchain_and_later_scoring(self):
        with patch("dragonhydra.child.ledger._utc_now", return_value=NOW):
            issued = self.ledger.append_prediction(self.proposal)
        self.assertEqual(issued["prediction_issued_at"], NOW.isoformat())
        before = (Path(self.temp.name) / "00000001.json").read_bytes()
        after = NOW + timedelta(hours=4)
        with patch("dragonhydra.child.ledger._utc_now", return_value=after):
            scored = self.ledger.append_outcome(issued["prediction_id"], Outcome.HOME,
                                                event_completed_at=NOW + timedelta(hours=3),
                                                availability=available(after), evidence_hash=HASH, synthetic=True)
        self.assertEqual((Path(self.temp.name) / "00000001.json").read_bytes(), before)
        self.assertEqual(scored["previous_hash"], issued["hash"])
        self.assertEqual(len(self.ledger.verify(expected_head=scored["hash"])), 2)
        self.assertAlmostEqual(scored["scores"]["MULTICLASS_BRIER"], 0.38)

    def test_backdating_and_reconstruction_and_future_inputs_refused(self):
        with patch("dragonhydra.child.ledger._utc_now", return_value=NOW), self.assertRaises(ValueError):
            self.ledger.append_prediction(replace(self.proposal, kickoff_at=NOW - timedelta(seconds=1)))
        with self.assertRaises(ValueError):
            replace(self.proposal, input_availability=(available(NOW, TemporalMode.RECONSTRUCTED_PIT),))
        with patch("dragonhydra.child.ledger._utc_now", return_value=NOW), self.assertRaises(ValueError):
            self.ledger.append_prediction(replace(self.proposal, input_availability=(available(NOW + timedelta(seconds=1)),)))
        self.assertEqual(self.ledger.verify(), ())

    def test_tamper_detection_against_hashchain_and_external_head(self):
        with patch("dragonhydra.child.ledger._utc_now", return_value=NOW):
            issued = self.ledger.append_prediction(self.proposal)
        with self.assertRaises(ValueError):
            self.ledger.verify(expected_head="b" * 64)
        path = Path(self.temp.name) / "00000001.json"
        data = json.loads(path.read_text())
        data["probabilities"] = [0.9, 0.05, 0.05]
        path.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaises(ValueError):
            self.ledger.verify(expected_head=issued["hash"])

    def test_outcome_cannot_precede_completion_or_mix_synthetic_real(self):
        with patch("dragonhydra.child.ledger._utc_now", return_value=NOW):
            issued = self.ledger.append_prediction(self.proposal)
        with patch("dragonhydra.child.ledger._utc_now", return_value=NOW), self.assertRaises(ValueError):
            self.ledger.append_outcome(issued["prediction_id"], Outcome.HOME, event_completed_at=NOW,
                                       availability=available(), evidence_hash=HASH, synthetic=True)
        after = NOW + timedelta(hours=4)
        with patch("dragonhydra.child.ledger._utc_now", return_value=after), self.assertRaises(ValueError):
            self.ledger.append_outcome(issued["prediction_id"], Outcome.HOME,
                                       event_completed_at=NOW + timedelta(hours=3), availability=available(after),
                                       evidence_hash=HASH, synthetic=False)

    def test_duplicate_outcome_and_lock_are_fail_closed(self):
        with patch("dragonhydra.child.ledger._utc_now", return_value=NOW):
            issued = self.ledger.append_prediction(self.proposal)
        after = NOW + timedelta(hours=4)
        kwargs = dict(event_completed_at=NOW + timedelta(hours=3), availability=available(after), evidence_hash=HASH, synthetic=True)
        with patch("dragonhydra.child.ledger._utc_now", return_value=after):
            self.ledger.append_outcome(issued["prediction_id"], Outcome.HOME, **kwargs)
            with self.assertRaises(ValueError):
                self.ledger.append_outcome(issued["prediction_id"], Outcome.AWAY, **kwargs)
        (Path(self.temp.name) / ".append.lock").write_text("synthetic-existing-lock")
        with self.assertRaises(FileExistsError):
            self.ledger.append_prediction(self.proposal)

    def test_ledger_storage_cannot_escape_child_runtime(self):
        with self.assertRaises(ValueError):
            PredictionLedger(ROOT / "docs/forbidden-ledger")

    def test_schedule_lower_bound_is_not_mislabeled_verified_kickoff(self):
        proposal = replace(self.proposal, synthetic=False, schedule_time_semantics="DATE_EARLIEST_GLOBAL_BOUND",
                           analysis_artifact_hash=HASH)
        with patch("dragonhydra.child.ledger._utc_now", return_value=NOW):
            issued = self.ledger.append_prediction(proposal)
        self.assertEqual(issued["decision_horizon"], "ACTUAL_PRE_SCHEDULE_LOWER_BOUND_TIMESTAMP")
        self.assertEqual(issued["analysis_artifact_hash"], HASH)
        self.ledger.verify(expected_head=issued["hash"])
        with self.assertRaises(ValueError):
            replace(proposal, analysis_artifact_hash=None)


if __name__ == "__main__":
    unittest.main()
