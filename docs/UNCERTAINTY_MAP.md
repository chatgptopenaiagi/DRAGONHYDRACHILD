# First-class uncertainty

Status: COMPLETE representation and reconciliation foundation. Numeric uncertainty reduction and predictive benefit are not inferred from model prose.

`UncertaintyMap` is a bounded typed collection of uniquely identified `UncertaintyState` objects. Each item contains dimension, optional score, status, provenance, reason codes, last-updated clock and recommended resolution. States include UNKNOWN, OPEN, RESOLVED and BLOCKED. Null means unknown, not zero risk or no uncertainty. Numeric values must lie in [0,1] and carry provenance.

Relevant dimensions include evidence coverage, temporal alignment, identity, model disagreement, market, lineup, source availability, calibration, research value, runtime and machine-state staleness. A dimension need not receive a number merely because a dashboard can display one. Scores are comparable only when their measurement definitions and provenance are comparable.

## Disagreement is preserved

[reconciliation.py](../src/dragonhydra/cognitive_v2/reconciliation.py) compares explicit subject/position pairs from different actors operating on the same frozen state and task. It preserves both complete claims, their references, confidence categories and assumptions. Equal strings indicate agreement about an explicit position; they do not establish external truth. Different positions remain DISAGREEMENT.

Outputs distinguish AGREEMENT, PARTIAL_AGREEMENT, DISAGREEMENT, INSUFFICIENT_EVIDENCE and NOT_COMPARABLE. Unknown references, unsupported claims, absent comparisons or incomplete actor results prevent a fabricated winner. Different assumptions and confidence conflicts are listed separately. Recommended measurement identifies disputed or unsupported subjects. No natural-language averaging or forced consensus occurs.

Reference membership proves that a claim points into the bounded snapshot. It does not generally prove that the cited evidence entails the claim. Where the adapter implements an exact event predicate, an UNSUPPORTED_BY_PROJECTION flag is retained as an unsupported claim during reconciliation. General entailment and eventual outcome correctness require further measurable evaluation. The system therefore retains WORLD_VALIDATION_REQUIRED even when both actors agree.

## Freshness uncertainty

An old machine observation is not silently refreshed by loading it. Snapshot use checks explicit expiry; failed probes remain failed. A semantic state hash may stay unchanged across two captures, while full receipt hashes and clocks still distinguish the observations. Machine-sensitive future operations must use fresh relevant preconditions and an authoritative current state.

## What closes an uncertainty

An accepted new observation, validated calculation or later outcome may justify a new state and an explicit superseding memory record. Merely producing another explanation does not resolve an uncertainty. Original predictions remain frozen. Measured learning requires the comparison contract described in [memory](COGNITIVE_MEMORY.md).
