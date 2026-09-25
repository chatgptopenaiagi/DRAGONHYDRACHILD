# Public machine context

This is a portable summary of the recorded laboratory, not a live inventory. Exact executable paths, host-specific identifiers, process IDs and bounded local observations belong only in the ignored local capsule.

| Component | Preserved context | Verification / limitation |
| --- | --- | --- |
| Host | Windows, native XAMPP/Apache/PHP with separate CHILD presentation | Current metadata must be compared locally |
| Python | 3.14 required; last recorded canonical interpreter 3.14.7 | Existing environment preserved; do not downgrade/install automatically |
| Compute | Existing NVIDIA/CUDA-capable runtime; 4B GPU and 30B hybrid CPU/GPU inference demonstrated | Device-wide resource samples; not isolated performance proof |
| Runtime | `llama-b10665-ca3d5a3e1`; pinned 54-binary manifest | [Runtime manifest](../../config/localai_runtime_manifest.json) |
| Model 4B | `qwen3-4b`, 2,497,280,256 bytes | SHA-256 below; historical publisher provenance UNKNOWN |
| Model 30B | `qwen3-coder-30b`, 18,556,689,568 bytes | SHA-256 below; matched surviving historical manifest |
| CHILD endpoint | Authenticated loopback gateway 8083, backend 8082 | Last V2 handoff READY; reobserve before reliance |
| Owner parallel endpoints | Ollama 11434, manual llama 11435 | Owner-authorized; preserve identity/ownership |
| Databases | CHILD-owned SQL Server and MariaDB resources on existing shared engines | No parent identity/database mutation |
| Scheduling | Existing CHILD prospective collector | Last V2 result 0/Ready; continuity does not modify it |

Known model hashes are reused from [V2 validation](../evidence/cognitive_v2_validation.json) and the [runtime audit](../LOCALAI_QWEN_RUNTIME.md); this preservation mission does not rehash multi-gigabyte weights.

```text
qwen3-4b:
7485fe6f11af29433bc51cab58009521f205840f5b4ae3a32fa7f92e8534fdf5
qwen3-coder-30b:
fadc3e5f8d42bf7e894a785b05082e47daee4df26680389817e2093056f088ad
```

The local capsule may record that credentials are required/present and their location class. It must never preserve their values. No GitHub token, gateway key, database password, cookie, private key or decrypted DPAPI material belongs in either mode.
