# Test index

Preservation-only validation: **36 targeted continuity tests passed**, with zero failures/errors/skips. Repository syntax/metadata and staged-link/safety checks accompany publication. The full CHILD suite and model experiments below are reused historical evidence and were not repeated for this mission.

**Last full foundation validation:** commit `8cfde5e7ca903cf187f646b6d43a3af283965e86`, tree `e6162e925da5eb97dc76546750677862b7655f0f`.

| Evidence | Recorded result | Reference |
| --- | --- | --- |
| Full CHILD suite | 694 passed = 681 portable + 13 local; 0 failures/errors/skips | [V2 progress](../COGNITIVE_V2_PROGRESS.md) |
| New V2 tests | 271 above recovery's 423 | [V2 progress](../COGNITIVE_V2_PROGRESS.md) |
| Portable guard | No prohibited live dependency access; exact staged tree matched committed tree | Local final handoff and staged receipt |
| Windows / Ubuntu CI | SUCCESS at exact known-good commit | [CI run](https://github.com/chatgptopenaiagi/DRAGONHYDRACHILD/actions/runs/36196235236) |
| Repository safety | SUCCESS at exact known-good commit | [Safety run](https://github.com/chatgptopenaiagi/DRAGONHYDRACHILD/actions/runs/36196238005) |
| LocalAI recovery | 423 = 410 portable + 13 local; 19/19 live checks | [Recovery audit](../LOCALAI_RECOVERY_AUDIT.md) |
| ARX experiment / interpretation | 8/8 and 4/4 | [V2 measurements](../evidence/cognitive_v2_validation.json) |
| Gateway / cockpit negatives | 12/12 | [V2 progress](../COGNITIVE_V2_PROGRESS.md) |
| Transient live failure | Concurrent health timed out during serial inference; idle retry passed | [V2 progress](../COGNITIVE_V2_PROGRESS.md) |
| Donor deployment tests | 37 inherited tests explicitly outside CHILD scope, not hidden as passing | [V2 progress](../COGNITIVE_V2_PROGRESS.md) |

Private evidence locators, relative to the project root:

```text
runtime/checkpoints/cognitive-awareness-v2-20260925T214532Z/final-handoff.json
runtime/checkpoints/cognitive-awareness-v2-20260925T214532Z/full-tests-release.log
runtime/checkpoints/cognitive-awareness-v2-20260925T214532Z/portable-final.log
runtime/checkpoints/cognitive-awareness-v2-20260925T214532Z/staged-check.json
runtime/checkpoints/cognitive-awareness-v2-20260925T214532Z/staged-portable.log
runtime/checkpoints/cognitive-awareness-v2-20260925T214532Z/repository-safety-final.json
runtime/checkpoints/cognitive-awareness-v2-20260925T214532Z/live-boundaries.json
```

The [structured test index](manifests/tests.json) preserves these references. Continuity changes use focused synthetic preservation tests and existing repository safety/link checks. Their final measured count belongs in the preservation handoff and capsule; the 694 figure remains historical, not a claim that the entire suite was rerun for preservation.
