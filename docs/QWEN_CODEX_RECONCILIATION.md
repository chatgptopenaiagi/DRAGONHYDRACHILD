# Qwen and Codex reconciliation V2

QWEN_4B, QWEN_30B and CODEX are distinct actors. Agreement is a comparison result, not external validation. The [reconciliation engine](../src/dragonhydra/cognitive_v2/reconciliation.py) preserves both actors' explicit claims, assumptions, confidence and references.

An actor result binds a frozen `state_hash`, task kind and creation time to conclusions, uncertainty references, hypotheses, research needs and proposals. Qwen results also carry pinned model/runtime identity, request hash, response hash and measured latency. Conclusions are structured advisory products. Neither actor can write external observations, frozen forecasts or MEDUSA acceptance through this interface.

Codex receives an explicit content-addressed request and frozen snapshot through the [artifact store](../src/dragonhydra/cognitive_v2/artifacts.py). Its response is a separate typed CODEX result referencing that state. Missing Codex work stays `CODEX_RESPONSE_UNAVAILABLE`. There is no private IPC, automatic API inference or substitution of a Qwen answer for a Codex answer.

Comparison first checks identical state hashes. Different actors and identical task kinds permit subject-level comparison. Matching positions are recorded as agreements; different positions remain disagreements. Different assumptions and confidence categories remain visible. Unknown references and uncited claims are flagged as unsupported. Missing overlap, incomplete actor results or unsupported claims produce `INSUFFICIENT_EVIDENCE`. Different tasks or the same actor produce `NOT_COMPARABLE`. Mixed agreement and disagreement can produce `PARTIAL_AGREEMENT`.

Reference membership proves only that a referenced object is present in the supplied state. It does not prove that the claim follows from the reference. One narrow measurable adapter check compares `PROCESS_STARTED` / `PROCESS_STOPPED` claims with their cited ARX transition codes (`PROCESS_STARTED` / `MODEL_RUNTIME_STARTED` and `PROCESS_STOPPED` / `MODEL_RUNTIME_STOPPED`). Unsupported transitions retain the original claim with `UNSUPPORTED_BY_PROJECTION`; reconciliation includes that flag among unsupported claims. A current PID alone does not prove a transition.

The current engine does not infer general semantic truth from prose, average language claims, assign a winner or automatically update mathematical model weights. Recommended measurements identify disputed subjects requiring further evidence. Existing research needs retain their HYDRA and MEDUSA requirements.

The model-facing Qwen projection is bounded and categorical; Codex can inspect the controlled full state artifact. A comparison receipt must retain the actual input/projection hashes and report that visibility difference. The live comparison in [progress](COGNITIVE_V2_PROGRESS.md) is task-specific and does not establish universal model superiority or predictive accuracy.

Later independent observation can support a measurable `LearningFeedback` record. That record preserves the original expectation and later observation separately. External/outcome learning requires MEDUSA validation, machine learning requires ARX provenance, and predictive accuracy gain requires an observed outcome with explicit scoring inputs. Changed model prose alone is not learning.

See [contracts](COGNITIVE_STATE_CONTRACTS.md), [memory](COGNITIVE_MEMORY.md), [hypothesis and research](HYPOTHESIS_RESEARCH_ENGINE.md), and [routing](QWEN_ROUTING.md).
