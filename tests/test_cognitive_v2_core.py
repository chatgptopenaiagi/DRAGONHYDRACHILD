"""Portable evidence, policy, memory and reconciliation invariants."""

from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from dragonhydra.cognitive_v2.contracts import (
    ActionProposal, CapabilityDescriptor, CapabilityState, CognitiveActorResult,
    CognitiveCycleReceipt, CognitiveStateSnapshot, ComponentState, Conclusion,
    ContractError, EvidenceReference, ExpectedInformationValue, Hypothesis,
    LearningFeedback, MachineState, MemoryState, Metric, ModelState, ProjectState,
    ResearchNeed, StateLabel, UncertaintyMap, UncertaintyState, WorldState,
    content_hash, ensure_fresh, snapshot_references,
)
from dragonhydra.cognitive_v2.memory import (
    DecisionMemory, EpisodeMemory, KnownLimitationMemory, LearningMemory,
    MemoryItem, MemoryStore, WorkingMemory, learning_memory,
)
from dragonhydra.cognitive_v2.policy import default_capabilities, evaluate_proposal
from dragonhydra.cognitive_v2.reconciliation import reconcile
from dragonhydra.cognitive_v2.research import information_priority, rank_research, transition_hypothesis

T0 = "2026-09-25T12:00:00Z"
T1 = "2026-09-25T12:01:00Z"
T2 = "2026-09-25T12:02:00Z"
END = "2026-09-25T12:10:00Z"
H = "a" * 64
J = "b" * 64


def snapshot():
    return CognitiveStateSnapshot(
        snapshot_id="snapshot-test", created_at=T0, as_of_at=T0, temporal_mode="PRESENT",
        world_state=WorldState(as_of_at=T0, evidence=(EvidenceReference(
            evidence_id="evidence-one", content_hash=H, observed_at=T0, available_at=T0,
            source_id="official", epistemic_state="OBSERVATION", medusa_accepted=True),)),
        machine_state=MachineState(machine_snapshot_hash=J, observed_at=T0, available_at=T0,
                                   expires_at=END, health="HEALTHY", components=(ComponentState(
                                       component_id="gpu", status="AVAILABLE", metrics=(Metric(name="vram", value=6144, unit="MiB", provenance_refs=("gpu",)),),
                                       labels=(StateLabel(name="driver", value="616.92"),)),)),
        project_state=ProjectState(project_id="child", branch="feature/test", head="a" * 40,
                                   working_tree="CLEAN", observed_at=T0, available_at=T0, expires_at=END),
        model_state=ModelState(), memory_state=MemoryState(),
        uncertainties=UncertaintyMap(items=(UncertaintyState(uncertainty_id="lineup", dimension="LINEUP",
                                    last_updated=T0, recommended_resolution="official-lineup"),)),
        capabilities=default_capabilities(), active_fixture="fixture-one", active_prediction="prediction-one")


def conclusion(position="MISSING", refs=("lineup",), **kwargs):
    return Conclusion(claim_id="claim-one", subject="LINEUP", position=position,
                      summary="Lineup remains uncertain.", evidence_refs=refs, **kwargs)


def actor(state, identity="CODEX", claim=None, **kwargs):
    pins = dict(model_id="qwen-test", model_hash=H, runtime_id="llama-test", runtime_hash=J,
                input_hash=state.state_hash, output_hash=H) if identity.startswith("QWEN") else {}
    return CognitiveActorResult(actor_id=identity, state_hash=state.state_hash,
                                task_kind="CRITIQUE_STATE", created_at=T0,
                                conclusions=(claim or conclusion(),), **pins, **kwargs)


def hypothesis(state=None):
    state = state or snapshot()
    return Hypothesis(hypothesis_id="hypothesis-one", statement_summary="Lineup may matter.",
                      created_by="CODEX", created_at=T0, state_hash=state.state_hash,
                      falsification_condition="Measured sensitivity is zero.", required_observation="official-lineup")


def need(state=None, **kwargs):
    state = state or snapshot()
    return ResearchNeed(need_id="need-one", created_by="CODEX", created_at=T0,
                        state_hash=state.state_hash, uncertainty_id="lineup",
                        required_observation="official-lineup", requested_hydra_head="lineup",
                        provenance_refs=("lineup",), **kwargs)


def proposal(state=None, action="REQUEST_CALCULATION", **kwargs):
    state = state or snapshot()
    return ActionProposal(proposal_id="proposal-one", actor_id="CODEX", created_at=T0,
                          expires_at=END, state_hash=state.state_hash, capability_id=action.lower(),
                          action_class=action, **kwargs)


def feedback(**kwargs):
    values = dict(feedback_id="feedback-one", created_at=T2, expected_at=T0, observed_at=T1,
                  available_at=T1, expected_hash=H, observation_hash=J,
                  expected_summary="Test process should appear.", observed_summary="Test process appeared.",
                  difference_summary="Observed process matched the bounded expectation.", contributor="SYSTEM",
                  source_refs=("probe-one",), observation_kind="MACHINE", validated_by="ARX", next_test="Repeat probe.")
    values.update(kwargs)
    return LearningFeedback(**values)


def episode(identity="episode-one", **kwargs):
    values = dict(memory_id=identity, created_at=T0, source_refs=("probe-one",), input_hashes=(H,),
                  reason_codes=("BOUNDED_EPISODE",), epistemic_state="INTERPRETATION", confidence="UNKNOWN",
                  summary="A bounded cycle completed.")
    values.update(kwargs)
    return EpisodeMemory(**values)


def test_store(root, **kwargs):
    # Test-only substitute for the fixed CHILD runtime boundary; production has no override.
    canonical_root = Path(root).resolve()
    with patch("dragonhydra.cognitive_v2.memory.MEMORY_ROOT", canonical_root):
        return MemoryStore(canonical_root / "memory", **kwargs)


class CognitiveV2CoreTests(unittest.TestCase):
    def test_snapshot_roundtrip(self):
        value = snapshot()
        self.assertEqual(CognitiveStateSnapshot.from_dict(json.loads(json.dumps(value.to_dict()))), value)

    def test_actor_roundtrip(self):
        value = actor(snapshot(), "QWEN_4B")
        self.assertEqual(CognitiveActorResult.from_dict(value.to_dict()), value)

    def test_nested_unknown_field_rejected(self):
        value = snapshot().to_dict()
        value["machine_state"]["shell"] = "run"
        with self.assertRaises(ContractError):
            CognitiveStateSnapshot.from_dict(value)

    def test_unknown_top_field_rejected(self):
        value = actor(snapshot()).to_dict()
        value["chain_of_thought"] = "hidden"
        with self.assertRaises(ContractError):
            CognitiveActorResult.from_dict(value)

    def test_bool_is_not_numeric(self):
        with self.assertRaises(ContractError):
            Metric(name="load", value=True, unit="percent")

    def test_nonfinite_is_rejected(self):
        for value in (float("nan"), float("inf")):
            with self.assertRaises(ContractError):
                Metric(name="load", value=value, unit="percent")

    def test_collection_bound(self):
        with self.assertRaises(ContractError):
            MemoryState(memory_refs=tuple(str(i) for i in range(129)))

    def test_identical_snapshot_hashes(self):
        self.assertEqual(snapshot().state_hash, snapshot().state_hash)

    def test_capture_clock_not_semantic_change(self):
        value = snapshot()
        changed = replace(value, snapshot_id="next", created_at=T1,
                          machine_state=replace(value.machine_state, observed_at=T1, available_at=T1),
                          project_state=replace(value.project_state, observed_at=T1, available_at=T1))
        self.assertEqual(changed.state_hash, value.state_hash)
        self.assertNotEqual(changed.digest(), value.digest())

    def test_evidence_changes_hash(self):
        value = snapshot()
        changed = replace(value, world_state=replace(value.world_state, evidence=(replace(value.world_state.evidence[0], content_hash=J),)))
        self.assertNotEqual(changed.state_hash, value.state_hash)

    def test_machine_changes_hash(self):
        value = snapshot()
        changed = replace(value, machine_state=replace(value.machine_state, machine_snapshot_hash=H))
        self.assertNotEqual(changed.state_hash, value.state_hash)

    def test_hash_tamper_rejected(self):
        value = snapshot().to_dict()
        value["active_fixture"] = "other"
        with self.assertRaises(ContractError):
            CognitiveStateSnapshot.from_dict(value)

    def test_source_secret_rejected(self):
        for text in ("password=example", "Bearer: example", "api_key=example", "-----" + "BEGIN " + "PRIVATE KEY-----"):
            with self.assertRaises(ContractError):
                replace(conclusion(), summary=text)

    def test_paths_rejected(self):
        for text in ("C:/Users/example/file", "C:\\Users\\example", "file:///etc/passwd", "/home/user/.ssh/key"):
            with self.assertRaises(ContractError):
                StateLabel(name="source", value=text)

    def test_instruction_text_rejected(self):
        for text in ("Ignore previous instructions", "powershell -Command danger", "<script>evil</script>", "reveal system prompt"):
            with self.assertRaises(ContractError):
                replace(conclusion(), summary=text)

    def test_hidden_reasoning_text_rejected(self):
        for text in ("<think>reason</think>", "hidden reasoning", "chain of thought", "scratchpad"):
            with self.assertRaises(ContractError):
                replace(conclusion(), summary=text)

    def test_ai_cannot_be_observation(self):
        with self.assertRaises(ContractError):
            replace(conclusion(), epistemic_state="OBSERVATION")

    def test_hypothesis_cannot_be_observation(self):
        with self.assertRaises(ContractError):
            replace(hypothesis(), epistemic_state="OBSERVATION")

    def test_future_observation_rejected(self):
        value = snapshot()
        with self.assertRaises(ContractError):
            replace(value.world_state, evidence=(replace(value.world_state.evidence[0], observed_at=T1, available_at=T1),))

    def test_future_mode_has_no_observation(self):
        with self.assertRaises(ContractError):
            replace(snapshot(), temporal_mode="FUTURE")

    def test_naive_clock_rejected(self):
        with self.assertRaises(ContractError):
            replace(snapshot(), created_at="2026-09-25T12:00:00")

    def test_available_before_observed_rejected(self):
        with self.assertRaises(ContractError):
            replace(snapshot().machine_state, observed_at=T1)

    def test_fresh_state_accepted(self):
        self.assertTrue(snapshot().assert_fresh(T1))

    def test_expired_machine_rejected(self):
        with self.assertRaisesRegex(ContractError, "MACHINE_STATE_STALE"):
            ensure_fresh(snapshot(), END)

    def test_expired_project_rejected(self):
        value = snapshot()
        value = replace(value, project_state=replace(value.project_state, expires_at=T1))
        with self.assertRaisesRegex(ContractError, "COGNITIVE_STATE_STALE"):
            ensure_fresh(value, T2)

    def test_failed_probe_rejected(self):
        value = snapshot()
        value = replace(value, machine_state=replace(value.machine_state, health="FAILED"))
        with self.assertRaisesRegex(ContractError, "MACHINE_PROBE_FAILED"):
            ensure_fresh(value, T1)

    def test_future_machine_clock_rejected(self):
        value = snapshot()
        with self.assertRaises(ContractError):
            replace(value, machine_state=replace(value.machine_state, observed_at=T1, available_at=T1))

    def test_unknown_uncertainty_is_not_zero(self):
        self.assertIsNone(snapshot().uncertainties.items[0].score)

    def test_uncertainty_score_needs_basis(self):
        with self.assertRaises(ContractError):
            replace(snapshot().uncertainties.items[0], score=0.7)

    def test_duplicate_uncertainty_rejected(self):
        value = snapshot().uncertainties.items[0]
        with self.assertRaises(ContractError):
            UncertaintyMap(items=(value, value))

    def test_qwen_identity_required(self):
        with self.assertRaisesRegex(ContractError, "QWEN_RESPONSE_INVALID"):
            replace(actor(snapshot()), actor_id="QWEN_30B")

    def test_blocked_actor_has_no_fabricated_output(self):
        with self.assertRaises(ContractError):
            replace(actor(snapshot()), result_status="BLOCKED", failure_state="MODEL_UNAVAILABLE")

    def test_blocked_actor_explicit(self):
        value = CognitiveActorResult(actor_id="QWEN_30B", state_hash=H, task_kind="CRITIQUE_STATE",
                                     created_at=T0, result_status="BLOCKED", failure_state="MODEL_UNAVAILABLE")
        self.assertEqual(value.conclusions, ())

    def test_embedded_hypothesis_state_binding(self):
        with self.assertRaises(ContractError):
            replace(actor(snapshot()), hypotheses=(replace(hypothesis(), state_hash=J),))

    def test_embedded_actor_identity_binding(self):
        with self.assertRaises(ContractError):
            replace(actor(snapshot()), hypotheses=(replace(hypothesis(), created_by="QWEN_4B"),))

    def test_disagreement_preserved(self):
        state = snapshot()
        result = reconcile(state, actor(state), actor(state, "QWEN_4B", conclusion("KNOWN")), T1)
        self.assertEqual(result.status, "DISAGREEMENT")
        self.assertEqual(result.disagreements[0].left_claim.position, "MISSING")
        self.assertEqual(result.disagreements[0].right_claim.position, "KNOWN")

    def test_agreement_not_truth_verdict(self):
        state = snapshot()
        result = reconcile(state, actor(state), actor(state, "QWEN_4B"), T1)
        self.assertEqual(result.status, "AGREEMENT")
        self.assertIn("WORLD_VALIDATION_REQUIRED", result.reason_codes)

    def test_unsupported_claim_insufficient(self):
        state = snapshot()
        result = reconcile(state, actor(state), actor(state, "QWEN_4B", conclusion(refs=("invented",))), T1)
        self.assertEqual(result.status, "INSUFFICIENT_EVIDENCE")
        self.assertEqual(result.unsupported_claims, ("QWEN_4B:claim-one",))

    def test_no_reference_insufficient(self):
        state = snapshot()
        result = reconcile(state, actor(state), actor(state, "QWEN_4B", conclusion(refs=())), T1)
        self.assertEqual(result.status, "INSUFFICIENT_EVIDENCE")

    def test_reconciliation_wrong_state_rejected(self):
        state = snapshot()
        with self.assertRaises(ContractError):
            reconcile(state, actor(state), replace(actor(state, "QWEN_4B"), state_hash=J), T1)

    def test_same_actor_not_independent(self):
        state = snapshot()
        self.assertEqual(reconcile(state, actor(state), actor(state), T1).status, "NOT_COMPARABLE")

    def test_measurably_unsupported_claim_preserved(self):
        state = snapshot()
        claim = replace(conclusion(), reason_codes=("UNSUPPORTED_BY_PROJECTION",))
        result = reconcile(state, actor(state), actor(state, "QWEN_4B", claim), T1)
        self.assertEqual(result.status, "INSUFFICIENT_EVIDENCE")
        self.assertIn("QWEN_4B:claim-one", result.unsupported_claims)
        self.assertEqual(result.agreements[0].right_claim, claim)

    def test_actor_cannot_self_certify_supported_hypothesis(self):
        value = replace(hypothesis(), status="SUPPORTED", supporting_refs=("claimed",))
        with self.assertRaisesRegex(ContractError, "MEDUSA_REQUIRED"):
            replace(actor(snapshot()), hypotheses=(value,))

    def test_actor_cannot_self_certify_fulfilled_research(self):
        value = replace(need(), status="FULFILLED", fulfillment_refs=("claimed",))
        with self.assertRaisesRegex(ContractError, "MEDUSA_REQUIRED"):
            replace(actor(snapshot()), research_needs=(value,))

    def test_assumptions_and_confidence_preserved(self):
        state = snapshot()
        result = reconcile(state, actor(state), actor(state, "QWEN_4B", conclusion(assumptions=("Lineup matters.",), confidence="HIGH")), T1)
        self.assertEqual(result.different_assumptions, ("LINEUP",))
        self.assertEqual(result.confidence_conflicts, ("LINEUP",))

    def test_hypothesis_transition_keeps_original(self):
        old = hypothesis()
        new = transition_hypothesis(old, "UNDER_TEST")
        self.assertEqual(old.status, "PROPOSED")
        self.assertEqual(new.status, "UNDER_TEST")

    def test_hypothesis_support_requires_observation(self):
        value = transition_hypothesis(hypothesis(), "UNDER_TEST")
        with self.assertRaisesRegex(ContractError, "MEDUSA_REQUIRED"):
            transition_hypothesis(value, "SUPPORTED", observation_refs=("guess",), known_observation_refs=())

    def test_hypothesis_support_remains_hypothesis(self):
        value = transition_hypothesis(hypothesis(), "UNDER_TEST")
        value = transition_hypothesis(value, "SUPPORTED", observation_refs=("observed",), known_observation_refs=("observed",))
        self.assertEqual(value.epistemic_state, "HYPOTHESIS")

    def test_terminal_hypothesis_immutable(self):
        value = transition_hypothesis(hypothesis(), "SUPERSEDED")
        with self.assertRaises(ContractError):
            transition_hypothesis(value, "UNDER_TEST")

    def test_research_provenance_required(self):
        with self.assertRaises(ContractError):
            replace(need(), provenance_refs=())

    def test_research_cannot_bypass_hydra(self):
        with self.assertRaisesRegex(ContractError, "HYDRA_REQUIRED"):
            need(requires_hydra=False)

    def test_research_cannot_bypass_medusa(self):
        with self.assertRaisesRegex(ContractError, "MEDUSA_REQUIRED"):
            need(requires_medusa=False)

    def test_unknown_research_value_stays_unknown(self):
        self.assertIsNone(information_priority(need()))

    def test_numeric_research_estimate_needs_basis(self):
        with self.assertRaises(ContractError):
            ExpectedInformationValue(expected_uncertainty_reduction=0.5)

    def test_research_rank_explicit(self):
        unknown = need()
        measured = replace(unknown, need_id="need-two", value=ExpectedInformationValue(
            expected_uncertainty_reduction=0.5, observation_cost=1, decision_relevance=0.8, basis_refs=("calculation",)))
        self.assertEqual(rank_research((unknown, measured))[0].need_id, "need-two")
        self.assertFalse(measured.value.measured)

    def test_arbitrary_shell_capability_denied(self):
        with self.assertRaises(ContractError):
            CapabilityDescriptor(capability_id="shell", actor="CODEX", action_class="RUN_ARBITRARY_COMMAND", enabled=True)

    def test_disabled_mutation_can_be_described(self):
        value = CapabilityDescriptor(capability_id="shell", actor="CODEX", action_class="RUN_ARBITRARY_COMMAND", enabled=False)
        self.assertFalse(value.enabled)

    def test_arbitrary_action_proposal_denied(self):
        with self.assertRaises(ContractError):
            proposal(action="DELETE_FILE")

    def test_proposal_acceptance_does_not_execute(self):
        state = snapshot()
        result = evaluate_proposal(proposal(state), state, T1)
        self.assertEqual(result.status, "PROPOSAL_ACCEPTED")
        self.assertFalse(result.executes_action)

    def test_proposal_stale_hash_denied(self):
        state = snapshot()
        result = evaluate_proposal(replace(proposal(state), state_hash=J), state, T1)
        self.assertEqual(result.reason_codes, ("STATE_CHANGED_SINCE_PROPOSAL",))

    def test_proposal_stale_machine_denied(self):
        state = snapshot()
        value = replace(proposal(state), expires_at="2026-09-25T13:00:00Z")
        result = evaluate_proposal(value, state, END)
        self.assertIn("MACHINE_STATE_STALE", result.reason_codes)

    def test_proposal_expiry_denied(self):
        state = snapshot()
        self.assertEqual(evaluate_proposal(proposal(state), state, END).status, "DENIED")

    def test_unknown_capability_denied(self):
        state = snapshot()
        result = evaluate_proposal(replace(proposal(state), capability_id="unregistered"), state, T1)
        self.assertEqual(result.status, "DENIED")

    def test_actor_cannot_use_other_identity_capability(self):
        state = snapshot()
        result = evaluate_proposal(replace(proposal(state), actor_id="QWEN_4B"), state, T1)
        self.assertEqual(result.status, "DENIED")

    def test_frequency_cap_denied(self):
        state = snapshot()
        result = evaluate_proposal(proposal(state), state, T1, recent_count=1)
        self.assertIn("FREQUENCY_LIMIT", result.reason_codes)

    def test_bad_machine_precondition_denied(self):
        state = snapshot()
        result = evaluate_proposal(proposal(state, precondition_hashes=(H,)), state, T1)
        self.assertEqual(result.status, "DENIED")

    def test_research_proposal_requires_validation_path(self):
        state = snapshot()
        result = evaluate_proposal(proposal(state, action="REQUEST_HYDRA_RESEARCH"), state, T1)
        self.assertEqual(result.status, "REQUIRES_REVIEW")
        self.assertIn("HYDRA_REQUIRED", result.reason_codes)
        self.assertIn("MEDUSA_REQUIRED", result.reason_codes)

    def test_memory_append_and_lookup(self):
        with tempfile.TemporaryDirectory() as root:
            store = test_store(root)
            value = episode()
            store.append(value, known_refs=("probe-one",))
            self.assertEqual(store.lookup(value.memory_id, now=T1).summary, value.summary)

    def test_memory_unknown_provenance_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaisesRegex(ContractError, "MEMORY_REFERENCE_MISSING"):
                test_store(root).append(episode(), known_refs=())

    def test_memory_duplicate_cannot_overwrite(self):
        with tempfile.TemporaryDirectory() as root:
            store = test_store(root)
            store.append(episode(), known_refs=("probe-one",))
            with self.assertRaises(ContractError):
                store.append(episode(), known_refs=("probe-one",))
            self.assertEqual(len(store.records()), 1)

    def test_memory_supersession_preserves_history(self):
        with tempfile.TemporaryDirectory() as root:
            store = test_store(root)
            store.append(episode(), known_refs=("probe-one",))
            store.append(episode("episode-two", supersedes="episode-one", created_at=T1), known_refs=("probe-one",))
            self.assertEqual(len(store.records()), 2)
            self.assertEqual(len(store.active(T2)), 1)

    def test_working_memory_expires(self):
        values = episode().to_dict()
        values.pop("kind")
        values["expires_at"] = T1
        value = WorkingMemory(**values)
        with tempfile.TemporaryDirectory() as root:
            store = test_store(root)
            store.append(value, known_refs=("probe-one",))
            self.assertEqual(store.active(T2), ())

    def test_working_memory_requires_expiry(self):
        values = episode().to_dict()
        values.pop("kind")
        with self.assertRaises(ContractError):
            WorkingMemory(**values)

    def test_memory_capacity_fails_closed(self):
        with tempfile.TemporaryDirectory() as root:
            store = test_store(root, max_records=1)
            store.append(episode(), known_refs=("probe-one",))
            with self.assertRaisesRegex(ContractError, "REQUEST_TOO_LARGE"):
                store.append(episode("two"), known_refs=("probe-one",))

    def test_memory_tamper_detected(self):
        with tempfile.TemporaryDirectory() as root:
            store = test_store(root)
            store.append(episode(), known_refs=("probe-one",))
            path = next(store.root.glob("*.json"))
            value = json.loads(path.read_text())
            value["item"]["summary"] = "Changed."
            path.write_text(json.dumps(value))
            with self.assertRaises(ContractError):
                store.records()

    def test_learning_requires_later_observation(self):
        with self.assertRaises(ContractError):
            feedback(observed_at=T0)

    def test_learning_requires_provenance(self):
        with self.assertRaises(ContractError):
            feedback(source_refs=())

    def test_learning_machine_not_prediction_gain(self):
        with self.assertRaises(ContractError):
            feedback(accuracy_gain=0.1)

    def test_learning_outcome_requires_medusa(self):
        with self.assertRaises(ContractError):
            feedback(observation_kind="OUTCOME")

    def test_accuracy_gain_requires_scores(self):
        with self.assertRaises(ContractError):
            feedback(observation_kind="OUTCOME", validated_by="MEDUSA", accuracy_gain=0.1,
                     outcome_ref="probe-one")

    def test_accuracy_gain_arithmetic_verified(self):
        value = feedback(observation_kind="OUTCOME", validated_by="MEDUSA", accuracy_gain=0.1,
                         outcome_ref="probe-one", prior_score=0.3, later_score=0.2, score_method="BRIER_LOWER_BETTER")
        self.assertAlmostEqual(value.accuracy_gain, 0.1)
        with self.assertRaises(ContractError):
            replace(value, accuracy_gain=0.2)

    def test_learning_memory_requires_feedback(self):
        value = learning_memory(feedback(), "learning-one")
        with tempfile.TemporaryDirectory() as root:
            store = test_store(root)
            with self.assertRaises(ContractError):
                store.append(value, known_refs=("probe-one",))
            store.append(value, known_refs=("probe-one",), feedback=feedback())
            self.assertEqual(store.lookup("learning-one", now=T2).kind, "LEARNING")

    def test_memory_five_layers(self):
        values = episode().to_dict()
        values.pop("kind")
        self.assertEqual(DecisionMemory(**values).kind, "DECISION")
        self.assertEqual(KnownLimitationMemory(**values).kind, "KNOWN_LIMITATION")

    def test_memory_outside_child_runtime_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaisesRegex(ContractError, "UNTRUSTED_CONTEXT"):
                MemoryStore(root)

    def test_memory_parent_target_rejected(self):
        from dragonhydra.cognitive_v2.memory import MEMORY_ROOT
        with self.assertRaises(ContractError):
            MemoryStore(MEMORY_ROOT.parents[2] / "DRAGONHYDRA" / "runtime" / "memory")

    def test_memory_path_traversal_rejected(self):
        from dragonhydra.cognitive_v2.memory import MEMORY_ROOT
        with self.assertRaises(ContractError):
            MemoryStore(MEMORY_ROOT / ".." / "escape")

    def test_memory_concurrent_writer_fails_closed(self):
        with tempfile.TemporaryDirectory() as root:
            store=test_store(root)
            lock=store.root/'.memory-writer.lock'
            lock.write_bytes(b'OTHER_WRITER')
            with self.assertRaisesRegex(ContractError,'AUDIT_FAILURE'):
                store.append(episode(),known_refs=('probe-one',))
            self.assertEqual(lock.read_bytes(),b'OTHER_WRITER')
            self.assertFalse(list(store.root.glob('*.json')))

    def test_memory_writer_lock_released_after_failure(self):
        with tempfile.TemporaryDirectory() as root:
            store=test_store(root)
            with self.assertRaises(ContractError):
                store.append(episode(),known_refs=())
            self.assertFalse((store.root/'.memory-writer.lock').exists())
            store.append(episode(),known_refs=('probe-one',))

    def test_all_cognitive_actors_have_analysis_capabilities(self):
        registry = default_capabilities().capabilities
        for identity in ("CODEX", "QWEN_4B", "QWEN_30B"):
            self.assertTrue(any(c.actor == identity and c.action_class == "ANALYZE_STATE" and c.enabled for c in registry))

    def test_machine_mutations_explicitly_disabled(self):
        from dragonhydra.cognitive_v2.policy import DISABLED_MUTATIONS
        registry = default_capabilities().capabilities
        for action in DISABLED_MUTATIONS:
            selected = [c for c in registry if c.action_class == action]
            self.assertEqual(len(selected), 3)
            self.assertFalse(any(c.enabled for c in selected))

    def test_analysis_descriptor_not_action_executor(self):
        with self.assertRaises(ContractError):
            proposal(action="ANALYZE_STATE")

    def test_receipt_roundtrip(self):
        value = CognitiveCycleReceipt(cycle_id="cycle-one", created_at=T0, as_of_at=T0,
                                      state_hash=H, snapshot_hash=H, machine_snapshot_hash=J,
                                      routing_hash=H, actor_result_hashes=(J,), result_status="COMPLETE",
                                      input_hash=H, output_hash=J)
        self.assertEqual(CognitiveCycleReceipt.from_dict(value.to_dict()), value)

    def test_snapshot_refs_bounded_known_only(self):
        refs = snapshot_references(snapshot())
        self.assertIn("evidence-one", refs)
        self.assertIn("lineup", refs)
        self.assertNotIn("invented", refs)


if __name__ == "__main__":
    unittest.main()
