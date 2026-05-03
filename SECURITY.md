# Security policy

`.apworld` packages are renamed `.zip` archives containing Python that runs on the host's machine during Archipelago multiworld generation and gameplay. A malicious APWorld could steal credentials, install malware, exfiltrate data, or compromise the host.

The upstream index CI checks **functional correctness** (Eijebong's fuzzer, sha256 lockfile). It does not audit the Python source for malicious patterns. This fork adds that layer.

## Audit policy

Every pull request that adds or updates an APWorld in this repository is run through an automated source-level security audit before review:

1. The proposed `.apworld` is downloaded and its sha256 is recorded.
2. Extraction runs in a sandboxed Docker container with no network access, read-only filesystem, capped memory, capped CPU, and a process limit. The sandbox blocks zip bombs and path traversal in member names.
3. Only `.py` files are extracted. The raw `.apworld` binary never leaves the sandbox.
4. The extracted source is reviewed against a pattern catalog covering: arbitrary code execution (`eval`, `exec`, dynamic `__import__`), system commands (`subprocess`, `os.system`, etc.), network access (`socket`, HTTP libraries), native code (`ctypes`, `.dll`/`.so`), unsafe deserialization (`pickle`, `yaml.load` without `SafeLoader`), filesystem writes outside the documented output directory, environment / credential access, module manipulation, signal/process spawning, obfuscated payloads, and prompt-injection text in source.
5. The result is one of three verdicts.

## Verdicts

- **PASS** -- no findings, or only `INFO` findings. Safe to merge from a code-review perspective; remaining checks (fuzzer, naming, semver) still apply.
- **NEEDS_REVIEW** -- one or more `WARNING` findings. The patterns are dual-use (e.g., localhost socket for in-game communication, mod-extraction zip handling in a client). A maintainer must read the report and confirm the intent is legitimate before merge.
- **FAIL** -- at least one `CRITICAL` finding. The PR is blocked pending either remediation by the author or rejection.

The audit report is posted as a PR comment. If the verdict is `NEEDS_REVIEW`, the report explains exactly which patterns triggered and what would justify them.

## Reporting a vulnerability

If you believe an indexed APWorld is malicious, or that a previously-merged audit missed a real issue:

- **Do not open a public issue** describing the exploit before the world has been removed from the index.
- Open a [private security advisory](https://github.com/dowlle/Archipelago-index/security/advisories/new) on this repository.
- Include the APWorld name and version, the file path or line number of concern, and a description of the risk.

For issues with the upstream community index, please also notify [mooinglemur/Archipelago-index](https://github.com/mooinglemur/Archipelago-index).

## Limitations

The audit is a code review, not proof of safety. Sophisticated obfuscation can evade pattern matching. Verdicts depend on the model's analysis and may vary slightly between re-runs. The audit covers `.py` source only -- bundled non-Python data files are not analyzed beyond size and presence.

The audit is one layer in a defence-in-depth posture, not a guarantee.
