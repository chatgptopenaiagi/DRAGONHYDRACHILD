# CHILD temporal continuum and prediction ledger

State: **PARTIAL / EXPERIMENTAL**. Epistemic/time contracts and local append-only ledger mechanics pass synthetic tests. Sustained prospective real prediction history, external trusted timestamping and outcome validation are not established by those tests.

## Epistemic continuum

[continuum.py](../src/dragonhydra/child/continuum.py) separates OBSERVATION, RECONSTRUCTION, DERIVED_FEATURE, PREDICTION, SIMULATION, MARKET_OBSERVATION and HYPOTHESIS. Each record keeps fixture identity, event time, full availability policy, source-evidence references and synthetic status.

The cursor selects by availability at the requested knowledge time and temporal mode. A future scheduled fixture may already be known; event time therefore does not itself gate knowledge. A later capture cannot appear in an earlier strict view. Reconstructed information cannot receive a genuine-observation label. The observed-fact gate refuses hypotheses, predictions, simulations, derived features, reconstructions and synthetic material.

This is a query/contract layer, not a new database or a source of truth independent of retained evidence.

## Prospective prediction ledger

[ledger.py](../src/dragonhydra/child/ledger.py) accepts only typed `LedgerProposal` objects with probabilities, canonical fixture reference, future kickoff, model/version, SHA-256 feature/evidence/code fingerprints, declared sources and STRICT_PIT input availability. It records synthetic status separately. Imported historical replay objects are not accepted.

`append_prediction` stamps the actual process clock; there is no caller-supplied `prediction_issued_at` argument. It rejects issuance at/after kickoff, reconstructed inputs and inputs unavailable at the actual append time. A clock reversal relative to prior entries fails closed.

Where a source supplies a calendar date but no verified kickoff timezone, the caller may instead supply a conservative earliest global-timezone bound. Such entries must explicitly use `schedule_time_semantics=DATE_EARLIEST_GLOBAL_BOUND` and `decision_horizon=ACTUAL_PRE_SCHEDULE_LOWER_BOUND_TIMESTAMP`; they never claim verified kickoff precision. The default is VERIFIED_KICKOFF. STRICT_PIT describes genuine input availability, not proof of scheduled-event timezone. Every real entry must also include a SHA-256 `analysis_artifact_hash` referencing the retained complete model, ensemble, uncertainty and explanation companion.

Each event is a newly created exclusive file under ignored CHILD `runtime`. Sequence, preceding hash, canonical JSON content hash and actual timestamp form a verifiable chain. Exclusive locking prevents simultaneous writers. Writes are flushed to disk. Existing events are never replaced by the append API. A crash may leave an incomplete file or lock; verification refuses to proceed silently, and recovery must preserve that failure evidence.

Outcome scoring appends a separate event. Completion and observation must follow kickoff, the outcome must be genuinely available, and synthetic/real classes must match the prediction. Repeated scoring of the same prediction is refused. Proper scores are log loss, normalized RPS and multiclass Brier. Correcting a previously recorded outcome requires a later explicit correction protocol; this version does not rewrite it.

The chain is tamper-evident when compared with a separately retained head hash. It is **not a digital signature, external time authority, proof of a trustworthy system clock or protection against an administrator rewriting the entire chain and its anchor**. A real prospective milestone should retain the head hash in an independently timestamped checkpoint or repository-safe summary without copying raw ledger contents into Git.

## Evidence and limitations

[Synthetic tests](../tests/test_child_intelligence.py) verify cursor leakage, epistemic separation, actual-clock issuance, backdating refusal, immutable earlier bytes after outcome append, hash mutation detection, duplicate-outcome refusal, source-class separation, writer-lock refusal and CHILD-runtime path confinement. Test clock patching is confined to test code and never represents a live prediction.

The shared intelligence suite has 25 passing Python 3.14 tests. No parent project file, parent database, parent ledger or parent checkpoint was changed. No new storage technology or dependency was introduced.

LOCAL FORENSIC EVIDENCE = ignored `runtime/checkpoints` and runtime ledger files. REPOSITORY-SAFE EVIDENCE = small sanitized summaries under `docs/evidence`; raw records, credentials and datasets remain local.

## Genuine CHILD issuance and source-bundle boundary

A real-source forecast was issued at `2026-09-24T20:55:34.109013+00:00` for the source-reported Manchester United–Tottenham fixture dated 2026-10-10. It uses the conservative date lower bound, not verified kickoff precision. [Curated validation](evidence/child-validation-summary.json) retains its immutable hash, evidence/model references and actual issue clock. SQL and the dashboard expose it; no actual outcome has been observed.

That first event predates exact source-bundle retention. Its code fingerprint is genuine, but this experiment does not claim its complete original uncommitted source bytes were archived. Later observatory calculations retain every source/config byte in a content-addressed local bundle, with a tested stable manifest hash. The first event is not rewritten to manufacture that missing history.

NEXT_EXACT_ACTION: retain the original hash anchor and append/evaluate the later genuinely observed result. Preserve the explicit observed-by upper bound if an exact final-whistle timestamp is unavailable.
