# Hypotheses and research value

Status: COMPLETE advisory foundation; measured real-world research benefit remains BLOCKED until later accepted evidence and evaluation exist.

The [research module](../src/dragonhydra/cognitive_v2/research.py) preserves this path:

AI hypothesis → ResearchNeed → permitted HYDRA acquisition → source observation → MEDUSA validation → accepted evidence → new state → cognitive reevaluation.

There is no direct AI-to-evidence operation. A model statement about a player's availability cannot update the factual player-availability field.

## Hypothesis lifecycle

`Hypothesis` records ID, short statement, actor, creation clock, originating state hash, supporting and contradicting references, assumptions, confidence, falsification condition and required observation. Its epistemic state is always HYPOTHESIS, including when its status becomes SUPPORTED.

The implemented states are PROPOSED, UNDER_TEST, SUPPORTED, WEAKENED, REJECTED, SUPERSEDED and UNRESOLVED. `transition_hypothesis` returns a new immutable version. It does not alter the original or any evidence. Support, weakening and rejection require references included in the caller's verified observation set; model claims alone cannot satisfy that set. Terminal superseded hypotheses cannot silently return to testing.

The trusted acquisition layer remains responsible for constructing the verified observation set from ARX or HYDRA/MEDUSA receipts. This foundation does not infer observation validity from a string that merely looks like an evidence ID.

## Research needs

`ResearchNeed` identifies the uncertainty, required observation, requested HYDRA head, originating actor/state, provenance, status and expected value. Fulfillment requires separate observation references. Both HYDRA and MEDUSA requirements are mandatory and cannot be disabled by Codex or Qwen. A requested head is a routing proposal, not permission to bypass its source policy. AI actor-result envelopes cannot self-advance a hypothesis to SUPPORTED or a need to FULFILLED; that requires the later trusted comparison path.

`ExpectedInformationValue` preserves null when uncertainty reduction, cost, latency or decision relevance is unknown. Numeric estimates require basis references. Estimates remain estimates unless explicitly supported as measured. Research ranking is deterministic:

`priority = expected_uncertainty_reduction × decision_relevance / (1 + observation_cost)`

Known values sort by descending priority; unknown values remain explicitly unknown and sort after supported estimates, with stable ID ordering for ties. Cost must use one comparable unit within a ranking set. This simple declared heuristic is neither expected monetary return nor demonstrated prediction improvement. Latency is recorded for review but is not silently blended into an unexplained score.

## Proposal policy

[policy.py](../src/dragonhydra/cognitive_v2/policy.py) exposes only NO_ACTION, REQUEST_HUMAN_REVIEW, REQUEST_HYDRA_RESEARCH, REQUEST_CALCULATION, REQUEST_STATE_REFRESH, REQUEST_MODEL_COMPARISON and REQUEST_MEMORY_LOOKUP. Proposal validation checks actor/capability identity, enablement, state hash, expiry, frequency and preconditions. Stale state yields STATE_CHANGED_SINCE_PROPOSAL or the applicable freshness failure.

The default registry describes CODEX, QWEN_4B and QWEN_30B independently. Each has three enabled analysis descriptors and seven proposal classes, alongside eight explicitly disabled machine-mutation descriptors. An analysis descriptor is not an action-execution opcode.

An accepted proposal does not execute anything. Research proposals require review through HYDRA and MEDUSA. Human-review proposals remain review requests. Arbitrary shell, registry, process termination, file mutation, installation, service control and privileged SQL have no enabled executor. Caller-supplied recent counts support policy checks; a future scheduler must maintain authoritative per-capability counters before unattended dispatch.

See [state contracts](COGNITIVE_STATE_CONTRACTS.md), [memory](COGNITIVE_MEMORY.md) and [uncertainty](UNCERTAINTY_MAP.md).
