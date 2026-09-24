"""Known answers, temporal canaries and reproducibility for CHILD's scientific path."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from math import log
import unittest

from dragonhydra.child.features import MatchEvidence, build_features, analytical_export
from dragonhydra.child.models import predict_models, glm_rates, knn_probabilities
from dragonhydra.child.simulation import score_matrix, scenario_mixture, monte_carlo
from dragonhydra.child.tribunal import compare, PastScore
from dragonhydra.child.evaluation import walk_forward, summarize
from dragonhydra.science.evaluation import Outcome, Probabilities
from dragonhydra.science.temporal import Availability, TemporalMode


UTC = timezone.utc
START = datetime(2020, 1, 1, tzinfo=UTC)


def availability(at, mode=TemporalMode.RECONSTRUCTED_PIT):
    capture = datetime(2026, 1, 1, tzinfo=UTC) if mode is TemporalMode.RECONSTRUCTED_PIT else at
    return Availability(mode, at, capture, capture, capture, "TEST_PUBLICATION_DELAY", "1", "SYNTHETIC_CONTROLLED_TEST", .8, "synthetic:test")


def match(number, home_goals=2, away_goals=1, mode=TemporalMode.RECONSTRUCTED_PIT):
    kickoff = START + timedelta(days=number*3)
    teams = ("a", "b", "c", "d")
    return MatchEvidence(f"r{number}", f"f{number}", "competition:test", teams[number%4], teams[(number+1)%4],
                         kickoff, kickoff+timedelta(hours=2), home_goals, away_goals,
                         availability(kickoff+timedelta(days=1), mode), availability(START-timedelta(days=10), mode))


class ChildFeatureTests(unittest.TestCase):
    def test_features_have_lineage_and_replay_hash(self):
        records = tuple(match(n) for n in range(10))
        target = match(10).target()
        first = build_features(target, records, target.kickoff_at, TemporalMode.RECONSTRUCTED_PIT)
        second = build_features(target, reversed(records), target.kickoff_at, TemporalMode.RECONSTRUCTED_PIT)
        self.assertEqual(first.snapshot_id, second.snapshot_id)
        self.assertEqual(len(first.features), 22)
        self.assertTrue(all(f.available_at is None or f.available_at <= target.kickoff_at for f in first.features))
        self.assertTrue(all(f.version and f.calculation_method for f in first.features))
        self.assertEqual(analytical_export(first)["snapshot"]["snapshot_id"], first.snapshot_id)

    def test_future_result_cannot_change_features(self):
        target = match(8).target()
        history = tuple(match(n) for n in range(8))
        old = build_features(target, history, target.kickoff_at, TemporalMode.RECONSTRUCTED_PIT)
        new = build_features(target, history+(match(20, 90, 0),), target.kickoff_at, TemporalMode.RECONSTRUCTED_PIT)
        self.assertEqual(old.snapshot_id, new.snapshot_id)

    def test_revision_returns_old_then_new(self):
        original = match(0)
        revised = replace(original, record_id="revision", home_goals=0, away_goals=4, revision=2,
                          supersedes_id=original.record_id, availability=availability(START+timedelta(days=20)))
        early, late = match(3).target(), match(9).target()
        self.assertEqual(build_features(early, (original, revised), early.kickoff_at, TemporalMode.RECONSTRUCTED_PIT).evidence[0].record_id, original.record_id)
        self.assertEqual(build_features(late, (original, revised), late.kickoff_at, TemporalMode.RECONSTRUCTED_PIT).evidence[0].record_id, revised.record_id)

    def test_strict_excludes_reconstructed_and_labels_survive(self):
        target = match(10, mode=TemporalMode.STRICT_PIT).target()
        snap = build_features(target, (match(0),), target.kickoff_at, TemporalMode.STRICT_PIT)
        self.assertEqual(snap.evidence, ())
        self.assertEqual(snap.values["home_history_missing"], 1)
        reconstructed = build_features(target, (match(0),), target.kickoff_at, TemporalMode.RECONSTRUCTED_PIT)
        self.assertEqual(reconstructed.to_dict()["evidence"][0]["availability"]["availability_mode"], "RECONSTRUCTED_PIT")

    def test_missing_external_facts_are_null(self):
        target = match(4).target()
        snap = build_features(target, (), target.kickoff_at, TemporalMode.RECONSTRUCTED_PIT)
        self.assertIsNone(snap.values["injury_burden"])
        self.assertEqual(snap.values["injury_burden_missing"], 1)
        self.assertEqual(snap.features[0].confidence, 0)

    def test_invalid_goals_and_unavailable_schedule_rejected(self):
        with self.assertRaises(ValueError): match(1, -1)
        row = match(4)
        target = replace(row.target(), schedule_availability=availability(row.kickoff_at+timedelta(days=1)))
        with self.assertRaises(ValueError): build_features(target, (), row.kickoff_at, TemporalMode.RECONSTRUCTED_PIT)

    def test_forged_future_snapshot_is_rejected(self):
        target = match(4).target()
        snap = build_features(target, (match(0),), target.kickoff_at, TemporalMode.RECONSTRUCTED_PIT)
        with self.assertRaises(ValueError): replace(snap, evidence=snap.evidence+(match(20),))
        with self.assertRaises(ValueError): replace(snap.features[0], value=float("inf"))


class ChildSimulationTests(unittest.TestCase):
    def test_poisson_symmetry_and_explicit_tail(self):
        dist = score_matrix(1., 1.)
        self.assertAlmostEqual(dist.probabilities.home, dist.probabilities.away, places=12)
        self.assertAlmostEqual(dist.matrix[0][0], 0.1353352832366127, places=12)
        self.assertAlmostEqual(dist.captured_mass+dist.tail_mass, 1., places=12)
        self.assertGreater(score_matrix(5, 5, max_goals=2).tail_mass, .9)

    def test_dixon_coles_probability_mass_and_rho_bounds(self):
        base, corrected = score_matrix(1.5, 1.2), score_matrix(1.5, 1.2, rho=-.1)
        self.assertAlmostEqual(base.captured_mass, corrected.captured_mass, places=12)
        self.assertGreater(corrected.probabilities.draw, base.probabilities.draw)
        with self.assertRaises(ValueError): score_matrix(1.5, 1.2, rho=1)
        with self.assertRaises(ValueError): score_matrix(float("nan"), 1)

    def test_scenario_mixture_is_hypothesis(self):
        mixture = scenario_mixture(((.5, score_matrix(2, 1)), (.5, score_matrix(1, 2))))
        self.assertAlmostEqual(mixture["probabilities"]["HOME"], mixture["probabilities"]["AWAY"], places=12)
        self.assertEqual(mixture["epistemic_state"], "HYPOTHESIS")
        with self.assertRaises(ValueError): scenario_mixture(((.6, score_matrix(1, 1)),))

    def test_monte_carlo_reproducibility_and_exact_agreement(self):
        first = monte_carlo(1.5, 1.2, samples=20000, seed=77)
        self.assertEqual(first, monte_carlo(1.5, 1.2, samples=20000, seed=77))
        exact = score_matrix(1.5, 1.2).probabilities.values
        for expected, measured in zip(exact, first["probabilities"].values()):
            self.assertLess(abs(expected-measured), .015)
        self.assertIn("sampling error", first["interval_meaning"])


class ChildModelTests(unittest.TestCase):
    def setUp(self):
        self.history = tuple(match(n, n%4, (n+1)%3) for n in range(12))
        self.target = match(13).target()
        self.snapshot = build_features(self.target, self.history, self.target.kickoff_at, TemporalMode.RECONSTRUCTED_PIT)
        self.frames = tuple((build_features(r.target(), self.history, r.kickoff_at, TemporalMode.RECONSTRUCTED_PIT), r) for r in self.history)

    def test_models_share_contract_and_valid_probabilities(self):
        forecasts = predict_models(self.snapshot, self.target, training_frames=self.frames)
        self.assertEqual(len(forecasts), 7)
        self.assertEqual(len({f.model_id for f in forecasts}), 7)
        self.assertTrue(all(f.feature_snapshot_id == self.snapshot.snapshot_id for f in forecasts))
        self.assertTrue(all(f.training_end < f.prediction_at for f in forecasts))
        self.assertTrue(all(abs(sum(f.probabilities.values)-1) < 1e-12 for f in forecasts))

    def test_glm_learns_training_home_goal_difference(self):
        history = tuple(match(n, 4, 0) for n in range(40))
        home, away = glm_rates(history, match(41).target())
        self.assertGreater(home, away*3)

    def test_knn_empty_history_is_uniform(self):
        self.assertEqual(knn_probabilities(self.snapshot, ()).values, (1/3, 1/3, 1/3))

    def test_future_training_frame_rejected(self):
        future = match(30)
        frame = build_features(future.target(), self.history, future.kickoff_at, TemporalMode.RECONSTRUCTED_PIT)
        with self.assertRaises(ValueError): predict_models(self.snapshot, self.target, training_frames=((frame, future),))

    def test_tribunal_does_not_use_future_score(self):
        forecasts = predict_models(self.snapshot, self.target)
        at = self.target.kickoff_at
        future = [PastScore(f.model_id, "past", at-timedelta(days=1), at+timedelta(hours=1), .1) for f in forecasts]
        compared = compare(forecasts, at, future, minimum_scores=1)
        self.assertEqual(set(compared["prior_score_counts"].values()), {0})
        self.assertEqual(set(compared["weights"].values()), {1/7})

    def test_loss_weights_use_only_evaluated_past(self):
        forecasts = predict_models(self.snapshot, self.target)
        at = self.target.kickoff_at
        past = [PastScore(f.model_id, "past", at-timedelta(days=2), at-timedelta(days=1), .1 if i==0 else 2.) for i, f in enumerate(forecasts)]
        compared = compare(forecasts, at, past, minimum_scores=1)
        self.assertGreater(compared["weights"][forecasts[0].model_id], compared["weights"][forecasts[1].model_id])
        self.assertGreaterEqual(compared["jensen_shannon_disagreement_nats"], 0)


class ChildEvaluationTests(unittest.TestCase):
    def test_metric_known_answers(self):
        report = summarize([(Probabilities(1/3, 1/3, 1/3), Outcome.HOME)])
        self.assertAlmostEqual(report["log_loss"], log(3))
        self.assertAlmostEqual(report["rps"], 5/18)
        self.assertAlmostEqual(report["brier"], 2/3)

    def test_replay_is_deterministic_and_assumptions_survive(self):
        history = tuple(match(n, n%3, (n+1)%3) for n in range(12))
        first = walk_forward(history, min_training=5)
        second = walk_forward(reversed(history), min_training=5)
        self.assertEqual(first["replay_hash"], second["replay_hash"])
        self.assertEqual(first["metrics"], second["metrics"])
        self.assertEqual(first["evaluation_matches"], 7)
        self.assertEqual(first["evidence_registry"]["r0"]["availability"]["availability_mode"], "RECONSTRUCTED_PIT")
        self.assertEqual(len(first["metrics"]), 11)
        self.assertIn("DEMONSTRATION_ONLY", first["inference_status"])

    def test_walk_forward_canary_does_not_change_earlier_predictions(self):
        history = tuple(match(n) for n in range(9))
        before = walk_forward(history, min_training=5)
        after = walk_forward(history+(match(30, 90, 0),), min_training=5)
        self.assertEqual([p["prediction_id"] for p in before["predictions"]],
                         [p["prediction_id"] for p in after["predictions"][:4]])

    def test_strict_rejects_backfilled_schedule(self):
        report = walk_forward(tuple(match(n) for n in range(8)), mode=TemporalMode.STRICT_PIT, min_training=2)
        self.assertEqual(report["evaluation_matches"], 0)
        self.assertEqual(len(report["skipped"]), 8)

    def test_tied_kickoffs_cannot_train_on_each_other(self):
        history = tuple(match(n) for n in range(6))
        next_row = match(6)
        twin = replace(next_row, record_id="twin", fixture_id="twin", home_team_id="c", away_team_id="d")
        report = walk_forward(history+(next_row, twin), min_training=5)
        target_rows = [p for p in report["predictions"] if p["fixture_id"] in ("f6", "twin")]
        self.assertEqual(len(target_rows), 2)
        self.assertTrue(all("r6" not in p["training_record_ids"] and "twin" not in p["training_record_ids"] for p in target_rows))
