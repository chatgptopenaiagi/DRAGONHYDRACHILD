"""Portable knowledge-boundary tests; no network, database or real ledger writes."""
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import unittest
from unittest.mock import patch

from dragonhydra.child import observatory
from dragonhydra.science.evaluation import Outcome
from dragonhydra.science.temporal import Availability, TemporalMode


NOW = datetime(2026, 9, 24, 20, tzinfo=timezone.utc)


def capture():
    def fixture(identifier, day, status, home_score=None, away_score=None):
        return {"fixture_id": identifier, "competition_id": "controlled-league",
                "home_team_id": "controlled-home", "away_team_id": "controlled-away",
                "match_date": day, "status": status, "home_score": home_score,
                "away_score": away_score, "temporal_mode": "STRICT_PIT", "synthetic": False,
                "snapshot_id": "controlled-capture", "content_hash": "a"*64,
                "observed_at": stamp, "retrieved_at": stamp, "available_at": stamp}
    stamp = (NOW-timedelta(hours=1)).isoformat()
    return {"snapshot": {"snapshot_id": "controlled-capture", "source_id": "controlled-test-source",
                         "source_url": "https://example.org/controlled-test-fixtures",
                         "observed_at": stamp, "retrieved_at": stamp, "available_at": stamp,
                         "content_hash": "a"*64, "temporal_mode": "STRICT_PIT"},
            "fixtures": [fixture("finished", "2026-09-21", "REPORTED_FINAL", 2, 1),
                         fixture("future", "2026-09-27", "SCHEDULED"),
                         fixture("unresolved-score", "2026-09-22", "SCHEDULED")]}


class FakeLedger:
    def __init__(self, events):
        self.events, self.appends = events, []

    def verify(self):
        return tuple(self.events)

    def append_outcome(self, prediction_id, outcome, **kwargs):
        self.appends.append((prediction_id, outcome, kwargs))
        return {"kind": "OUTCOME", "prediction_id": prediction_id, "outcome": outcome.value}


class ChildObservatoryTests(unittest.TestCase):
    def test_code_archive_retains_old_bytes_across_source_edits(self):
        import tempfile
        from pathlib import Path
        from dragonhydra.child.observatory import archive_calculation_code
        from dragonhydra.science.prospective import RawEvidenceStore
        import json
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'src').mkdir();(root/'config').mkdir()
            code=root/'src/model.py';code.write_bytes(b'VERSION = 1\n')
            original=archive_calculation_code(root)
            self.assertEqual(original,archive_calculation_code(root))
            code.write_bytes(b'VERSION = 2\n')
            self.assertNotEqual(original,archive_calculation_code(root))
            store=RawEvidenceStore(root/'runtime/child/code')
            manifest=json.loads(store.get(original))
            self.assertEqual(store.get(manifest['files']['src/model.py']),b'VERSION = 1\n')
    def test_strict_current_inputs_preserve_actual_capture_clocks(self):
        source = capture()
        before = deepcopy(source)
        rows, availability = observatory.strict_inputs(source, constructed_at=NOW)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].fixture_id, "finished")
        self.assertEqual(rows[0].outcome, Outcome.HOME)
        self.assertEqual(availability.availability_mode, TemporalMode.STRICT_PIT)
        self.assertEqual(availability.available_at, NOW)
        self.assertEqual(availability.ingested_at, NOW)
        self.assertEqual(availability.observed_at, NOW-timedelta(hours=1))
        self.assertEqual(availability.retrieved_at, NOW-timedelta(hours=1))
        self.assertIn("not verified kickoff/final-whistle", availability.assumption_reason)
        self.assertFalse(availability.eligible(NOW-timedelta(microseconds=1), TemporalMode.STRICT_PIT))
        self.assertEqual(source, before)

    def test_capture_after_construction_is_rejected(self):
        source = capture()
        source["snapshot"]["retrieved_at"] = (NOW+timedelta(seconds=1)).isoformat()
        with self.assertRaises(ValueError): observatory.strict_inputs(source, constructed_at=NOW)

    def test_snapshot_availability_cannot_be_pulled_backward(self):
        source = capture()
        source["snapshot"]["available_at"] = (NOW+timedelta(seconds=1)).isoformat()
        with self.assertRaises(ValueError): observatory.strict_inputs(source, constructed_at=NOW)

    def test_reconstructed_capture_or_record_cannot_become_strict(self):
        for location in ("snapshot", "fixture"):
            source = capture()
            row = source["snapshot"] if location == "snapshot" else source["fixtures"][0]
            row["temporal_mode"] = "RECONSTRUCTED_PIT"
            with self.subTest(location=location), self.assertRaises(ValueError):
                observatory.strict_inputs(source, constructed_at=NOW)

    def test_synthetic_record_cannot_lose_its_classification(self):
        source = capture()
        source["fixtures"][0]["synthetic"] = True
        with self.assertRaises(ValueError): observatory.strict_inputs(source, constructed_at=NOW)

    def test_fixture_capture_identity_and_content_must_agree(self):
        for change in ({"snapshot_id": "other-capture"}, {"content_hash": "b"*64},
                       {"available_at": (NOW+timedelta(seconds=1)).isoformat()}):
            source = capture()
            source["fixtures"][0].update(change)
            with self.subTest(change=change), self.assertRaises(ValueError):
                observatory.strict_inputs(source, constructed_at=NOW)

    def test_current_day_completion_proxy_is_not_prematurely_used(self):
        source = capture()
        source["fixtures"][0]["match_date"] = NOW.date().isoformat()
        rows, _ = observatory.strict_inputs(source, constructed_at=NOW)
        self.assertEqual(rows, ())

    def test_target_is_earliest_global_date_bound_not_verified_kickoff(self):
        source = capture()
        _, availability = observatory.strict_inputs(source, constructed_at=NOW)
        target, metadata = observatory.select_target(source, availability, at=NOW)
        expected = datetime(2026, 9, 26, 10, tzinfo=timezone.utc)
        self.assertEqual(target.fixture_id, "future")
        self.assertEqual(target.kickoff_at, expected)
        self.assertEqual(metadata["earliest_global_date_bound"], expected.isoformat())
        self.assertEqual(metadata["schedule_time_semantics"], "DATE_EARLIEST_GLOBAL_BOUND")
        self.assertIs(metadata["actual_utc_kickoff_verified"], False)

    def test_target_one_hour_safety_buffer_is_strict(self):
        source = capture()
        source["fixtures"] = [source["fixtures"][1]]
        lower = datetime(2026, 9, 26, 10, tzinfo=timezone.utc)
        _, availability = observatory.strict_inputs(source, constructed_at=NOW)
        with self.assertRaises(ValueError):
            observatory.select_target(source, availability, at=lower-timedelta(hours=1))
        selected, _ = observatory.select_target(source, availability, at=lower-timedelta(hours=1, microseconds=1))
        self.assertEqual(selected.kickoff_at, lower)

    def test_controlled_research_retains_synthetic_and_unvalidated_labels(self):
        with patch.object(observatory, "_now", return_value=NOW):
            report = observatory.controlled_research("controlled-fixture", NOW+timedelta(hours=2))
        result = report["result"]
        self.assertEqual(report["label"], "SYNTHETIC_CONTROLLED_RESEARCH_LOOP")
        self.assertEqual(result["state"], "VALIDATED_RECALCULATED")
        self.assertIs(result["synthetic"], True)
        self.assertIs(result["real_world_benefit_proven"], False)
        self.assertEqual(result["completeness_before"], .5)
        self.assertEqual(result["completeness_after"], 1.)
        self.assertAlmostEqual(result["entropy_reduction"], result["entropy_before"]-result["entropy_after"])
        self.assertGreater(result["entropy_reduction"], 0)
        self.assertIn("UNMEASURED", report["real_world_accuracy_gain"])

    def test_expired_controlled_research_does_not_claim_recalculation(self):
        with patch.object(observatory, "_now", return_value=NOW):
            report = observatory.controlled_research("controlled-fixture", NOW)
        self.assertEqual(report["result"]["state"], "DEADLINE_EXPIRED")
        self.assertIsNone(report["result"]["entropy_after"])
        self.assertEqual(report["result"]["completeness_after"], .5)
        self.assertEqual(report["label"], "SYNTHETIC_CONTROLLED_RESEARCH_LOOP")

    def test_future_control_answer_is_rejected_before_recalculation(self):
        constructor = observatory.ResearchAnswer
        def future_answer(*args, **kwargs):
            answer = constructor(*args, **kwargs)
            future = NOW+timedelta(seconds=1)
            availability = Availability(TemporalMode.STRICT_PIT, future, future, future, future,
                                        "SYNTHETIC_CONTROL_CLOCK", "1", "controlled future canary", 1, answer.source_id)
            return replace(answer, availability=availability)
        with patch.object(observatory, "_now", return_value=NOW), patch.object(observatory, "ResearchAnswer", side_effect=future_answer):
            report = observatory.controlled_research("controlled-fixture", NOW+timedelta(hours=2))
        self.assertEqual(report["result"]["state"], "REJECT")
        self.assertIsNone(report["result"]["entropy_after"])
        self.assertIs(report["result"]["real_world_benefit_proven"], False)

    def test_outcome_capture_is_upper_bound_not_fabricated_whistle_time(self):
        source = capture()
        _, availability = observatory.strict_inputs(source, constructed_at=NOW)
        event = {"kind": "PREDICTION", "prediction_id": "prediction", "fixture_id": "finished",
                 "kickoff_at": "2026-09-20T10:00:00+00:00", "synthetic": False}
        ledger = FakeLedger([event])
        outcomes = observatory.append_available_outcomes(source, ledger, availability)
        self.assertEqual(len(outcomes), 1)
        identifier, outcome, kwargs = ledger.appends[0]
        self.assertEqual((identifier, outcome), ("prediction", Outcome.HOME))
        self.assertEqual(kwargs["event_completed_at"], availability.observed_at)
        self.assertIn("observed-by upper bound", kwargs["availability"].assumption_reason)
        self.assertEqual(kwargs["evidence_hash"], source["snapshot"]["content_hash"])
        self.assertIs(kwargs["synthetic"], False)

    def test_outcome_already_scored_synthetic_or_not_finished_is_not_appended(self):
        source = capture()
        _, availability = observatory.strict_inputs(source, constructed_at=NOW)
        prediction = {"kind": "PREDICTION", "prediction_id": "prediction", "fixture_id": "finished",
                      "kickoff_at": "2026-09-20T10:00:00+00:00", "synthetic": False}
        variations = ([prediction, {"kind": "OUTCOME", "prediction_id": "prediction"}],
                      [{**prediction, "synthetic": True}], [{**prediction, "fixture_id": "future"}])
        for events in variations:
            ledger = FakeLedger(events)
            self.assertEqual(observatory.append_available_outcomes(source, ledger, availability), [])
            self.assertEqual(ledger.appends, [])

    def test_outcome_same_source_day_or_pre_bound_capture_waits(self):
        source = capture()
        _, availability = observatory.strict_inputs(source, constructed_at=NOW)
        event = {"kind": "PREDICTION", "prediction_id": "prediction", "fixture_id": "finished",
                 "kickoff_at": "2026-09-20T10:00:00+00:00", "synthetic": False}
        for same_day in (False, True):
            changed = deepcopy(source)
            checked = dict(event)
            if same_day:
                changed["fixtures"][0]["match_date"] = availability.observed_at.date().isoformat()
            else:
                checked["kickoff_at"] = (availability.observed_at+timedelta(hours=1)).isoformat()
            ledger = FakeLedger([checked])
            self.assertEqual(observatory.append_available_outcomes(changed, ledger, availability), [])
            self.assertEqual(ledger.appends, [])
