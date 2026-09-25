# Continuity security boundary

The continuity system observes and indexes. It does not restore services, execute a model, mutate Windows, reinstall packages, control processes, change Git state or acquire new external evidence.

## What may be public

Reviewed architecture/decision indexes, small sanitized measured summaries, known model/runtime hashes, portable Git identities, schema definitions, code and synthetic tests. Public records use repository-relative references and abstract location classes for private assets. Public evidence does not include personal executable paths or current host identifiers.

## What stays local

Bounded machine metadata, relevant process/listener identities, exact approved paths, local evidence locators and capsule integrity manifests remain under ignored `runtime/continuity/`. Capsules reference existing large checkpoints, model weights and databases; they do not copy them. Only selected small non-secret files are hashed. Previously validated model hashes retain their source and age rather than pretending to be new measurements.

Neither mode may contain plaintext API/GitHub/gateway tokens, passwords, authentication headers, cookies, private certificates, private keys or decrypted DPAPI. Secret-bearing files are represented by presence/location-class metadata only; their content is not read or copied. A local capsule is not a credential backup.

## Integrity and resource limits

Canonical JSON and SHA-256 identify capsule content; manifests bind selected files and repository identities. Capsules are immutable, with a separate latest pointer. Ordinary hashes provide change detection, not identity signatures, secure backups or protection against a hostile administrator replacing both data and anchors.

`verify` checks local schema/identity, file membership, sizes, content hashes and Git-reference syntax. It does not fetch Git objects, verify signatures or rehash models. Check the preserved commit against the current checkout separately during reactivation. A copied capsule does not prove its original machine still exists.

Capture and comparison are bounded to the repository and selected existing project-relevant paths/probes. No recursive whole-drive scan, multi-gigabyte model hash, model inference, full test rerun, compression of weights or database copying is needed. Failures and missing evidence remain explicit.

The complete runtime security model remains [Cognitive V2 security](../COGNITIVE_SECURITY_MODEL.md). This mission adds no runtime cognitive capability and cannot grant Qwen or artifact CODEX shell/filesystem/SQL/service authority.

Publication checks must inspect tracked paths, ignored capsule paths, small-file size limits, secret/path safety and actual staged Markdown targets. Runtime references in these indexes are plain locators, not broken repository hyperlinks. Local private state never enters Git just because a capture succeeded.
