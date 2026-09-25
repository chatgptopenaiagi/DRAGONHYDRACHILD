# Dual continuity memory

Read [NEXT_ACTION](NEXT_ACTION.md), then [CURRENT_STATE](CURRENT_STATE.md). These small indexes preserve engineering context; they do not authorize development or restore a machine.

| Mode | Purpose | Boundary |
| --- | --- | --- |
| GitHub continuity | Portable project state, decisions, evidence indexes and continuation contract. | Reviewed source and small non-secret manifests in this directory. |
| Local capsule | Machine-specific paths, bounded observations, local evidence references and integrity hashes. | Immutable directories under ignored `runtime/continuity/capsules/`; never committed. |

Both modes share project, schema, capture and Git identities. The public resume manifest may identify a particular local capsule and its manifest hash. It does not copy private machine manifests. Captures made later remain local until an explicit reviewed publication updates the public index.

Use Python 3.14 with bytecode disabled:

```text
python -B scripts/continuity.py capture
python -B scripts/continuity.py status
python -B scripts/continuity.py verify
python -B scripts/continuity.py resume-info
python -B scripts/continuity.py compare
```

These operations capture and compare bounded state. They never start models, run inference, install dependencies, reset Git, acquire sources or repair Windows. See the [resume protocol](RESUME_PROTOCOL.md), [security boundary](SECURITY_BOUNDARY.md), [artifact index](ARTIFACT_INDEX.md) and [machine context](MACHINE_CONTEXT_PUBLIC.md).

The public records preserve baseline `8cfde5e`, rather than guessing their own future enclosing commit. A future reader obtains the continuity implementation's commit from Git; local publication receipts can record the exact resulting HEAD. Existing scientific and historical documents retain their original dated claims.
