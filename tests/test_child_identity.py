"""Source-scoped alias identity tests; alternate names are synthetic test declarations."""

from copy import deepcopy
from datetime import datetime, timedelta
import unittest

from dragonhydra.child.identity import (
    IDENTITY_SCOPE, append_declared_alias, load_document, registry_records,
    resolve_in_registry, resolve_team, validate_registry,
)
from dragonhydra.science.entities import ResolutionMethod, ReviewState, team_id


class ChildIdentityTests(unittest.TestCase):
    def setUp(self):
        self.document = load_document()
        self.created = datetime.fromisoformat(self.document["created_at"])
        self.team = self.document["teams"][0]

    def alias(self, document, name, canonical_id, at, review_state=ReviewState.CONFIRMED):
        return append_declared_alias(document, alias=name, canonical_id=canonical_id,
                                     recorded_at=at, source_observed_at=at,
                                     source_hash="f" * 64, source_policy_version="synthetic-alias-review/1",
                                     review_reason="Synthetic test declaration only", review_state=review_state)

    def test_twenty_curated_aliases_preserve_preexisting_source_uuid_exactly(self):
        self.assertEqual(len(self.document["teams"]), 20)
        self.assertEqual(len(self.document["crosswalks"]), 20)
        self.assertEqual(self.document["identity_scope"], IDENTITY_SCOPE)
        for row in self.document["teams"]:
            result = resolve_team(row["display_name"], self.created)
            self.assertTrue(result.resolved)
            self.assertEqual(str(result.canonical_id), row["canonical_id"])
            self.assertEqual(result.canonical_id, team_id("openfootball:en.1", row["founding_declared_key"]))
            self.assertEqual(result.resolution_method, ResolutionMethod.DECLARED_ALIAS)

    def test_exact_normalization_allowed_but_unknown_or_similar_names_unresolved(self):
        name = self.team["display_name"]
        resolved = resolve_in_registry(self.document, "  " + name.upper() + "  ", self.created)
        self.assertEqual(str(resolved.canonical_id), self.team["canonical_id"])
        for unknown in ("Unknown Team", name + " reserve", name.removesuffix(" FC") + " guessed alias"):
            result = resolve_in_registry(self.document, unknown, self.created)
            self.assertFalse(result.resolved)
            self.assertEqual(result.resolution_method, ResolutionMethod.UNRESOLVED)

    def test_reviewed_rename_keeps_uuid_and_old_history_with_versioned_metadata(self):
        later = self.created + timedelta(hours=1)
        original = deepcopy(self.document)
        revised = self.alias(self.document, "Synthetic Renamed Club", self.team["canonical_id"], later)
        self.assertEqual(self.document, original)
        self.assertEqual(revised["registry_version"], 2)
        self.assertFalse(resolve_in_registry(revised, "Synthetic Renamed Club", later - timedelta(seconds=1)).resolved)
        renamed = resolve_in_registry(revised, "Synthetic Renamed Club", later)
        self.assertEqual(str(renamed.canonical_id), self.team["canonical_id"])
        self.assertEqual(str(resolve_in_registry(revised, self.team["display_name"], later).canonical_id), self.team["canonical_id"])
        self.assertEqual(revised["crosswalks"][:-1], original["crosswalks"])
        self.assertEqual(revised["crosswalks"][-1]["source_hash"], "f" * 64)
        self.assertEqual(revised["crosswalks"][-1]["recorded_at"], later.isoformat())

    def test_ambiguous_and_unconfirmed_aliases_remain_unresolved(self):
        later = self.created + timedelta(hours=1)
        first = self.alias(self.document, "Synthetic Same Name", self.team["canonical_id"], later)
        ambiguous = self.alias(first, "synthetic same name", self.document["teams"][1]["canonical_id"], later)
        result = resolve_in_registry(ambiguous, "SYNTHETIC SAME NAME", later)
        self.assertFalse(result.resolved)
        self.assertEqual(result.reason_code, "AMBIGUOUS_NAME")
        pending = self.alias(self.document, "Synthetic Pending Alias", self.team["canonical_id"], later, ReviewState.PENDING)
        self.assertFalse(resolve_in_registry(pending, "Synthetic Pending Alias", later).resolved)

    def test_knowledge_cursor_prevents_backfill_and_rejects_naive_or_backdated_review(self):
        self.assertFalse(resolve_team(self.team["display_name"], self.created - timedelta(microseconds=1)).resolved)
        with self.assertRaises(ValueError):
            resolve_team(self.team["display_name"], self.created.replace(tzinfo=None))
        with self.assertRaises(ValueError):
            self.alias(self.document, "Synthetic Backdate", self.team["canonical_id"], self.created - timedelta(seconds=1))
        bad = deepcopy(self.document)
        bad["crosswalks"][0]["source_observed_at"] = (self.created + timedelta(seconds=1)).isoformat()
        with self.assertRaises(ValueError):
            validate_registry(bad)

    def test_schema_and_sql_projection_preserve_declaration_not_provider_identity_claim(self):
        for mutate in (lambda d: d.update(schema_version=2), lambda d: d.update(provider="other-provider"),
                       lambda d: d["source_observation"].update(content_hash="invalid"),
                       lambda d: d["crosswalks"][0].update(resolution_method="EXACT_PROVIDER_ID"),
                       lambda d: d["teams"][0].update(founding_declared_key="Different original key")):
            bad = deepcopy(self.document)
            mutate(bad)
            with self.subTest(bad=bad["schema_version"]), self.assertRaises(ValueError):
                validate_registry(bad)
        records = registry_records()
        self.assertEqual(len(records), 20)
        self.assertTrue(all(row["entity_type"] == "team" and row["identity_scope"] == IDENTITY_SCOPE for row in records))
        self.assertEqual(records[0]["crosswalks"][0]["review_state"], "CONFIRMED")
        self.assertEqual(records[0]["source_observation"]["content_hash"], self.document["source_observation"]["content_hash"])


if __name__ == "__main__":
    unittest.main()
