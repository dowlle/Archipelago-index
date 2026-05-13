# Archipelago-index (dowlle fork)

A downstream fork of [mooinglemur/Archipelago-index](https://github.com/mooinglemur/Archipelago-index), the community-curated index of Archipelago Multiworld APWorld releases. This fork exists to:

1. **Sync from the MooingLemur upstream**, so a personal copy stays current without depending on anyone's downtime.
2. **Run an automated source-level security audit** on every APWorld update that lands here. The audit verdict is posted on each PR. See [`SECURITY.md`](./SECURITY.md) for the audit policy.

## Where to request new APWorlds

> [!IMPORTANT]
> **Open community contributions go to the upstream:** [mooinglemur/Archipelago-index](https://github.com/mooinglemur/Archipelago-index).
> Open your PR there. Dowlle syncs MooingLemur's `main` into this fork.

PRs opened directly here are welcome but the same change will need to land upstream to reach the wider ecosystem. See [`CONTRIBUTING.md`](./CONTRIBUTING.md) for more.

## TOML schema (for reference)

The index format is unchanged from upstream on the required fields, with three optional additions that downstream tooling can surface (stability badge, setup guide link, tracker link). A world entry lives at `index/{apworld}.toml` and looks like this:

```toml
name = "A Link to the Past"        # required; must match the world name used in YAML
display_name = "ALttP"             # optional; pretty name when `name` is ugly (e.g., "Manual_Foo_Bar")
home = "https://discord.com/..."   # optional; discord thread, github repo, or other canonical URL
tags = ["ad"]                      # optional; "ad" = after-dark server
stability = "stable"               # optional; "stable" | "unstable" | "alpha" | "beta"
setup_guide = "https://..."        # optional; URL to the author's setup / installation guide
tracker = "https://..."            # optional; URL to a PopTracker pack or similar

[versions]
"0.1.0" = { url = "https://github.com/foo/bar/releases/download/0.1.0/foo.apworld" }
"0.2.0" = { local = "../apworlds/foo-0.2.0.apworld" }
```

Filename rule: `{apworld}.toml` MUST match the apworld name. For "A Link to the Past" with apworld `alttp`, the file is `alttp.toml`.

### Optional metadata fields

These three fields are forward-compatible additions: existing TOMLs without them parse fine and downstream tools should treat them as missing rather than as defaults.

- **`stability`** — author-declared stability tag. Valid values are `stable`, `unstable`, `alpha`, `beta`. Sourced initially from the unofficial AP APWorld Google Sheet's "Stability" column. Renderers can use this to badge the apworld in their UI. Defaults to "unknown" if absent.
- **`setup_guide`** — direct URL to a setup / installation guide for the apworld. Usually a wiki page or a setup-en.md in the apworld repo. Renderers can link this next to the version pin so hosts find it without hunting.
- **`tracker`** — direct URL to a PopTracker pack or similar tracker resource. Renderers can link this next to the apworld's version pin.

### Versions

Each version key MUST be valid [semver](https://semver.org/) so versions can be ordered. It does not matter whether the actual APWorld respects semver — be creative if you must:

- A release tagged `0.8` becomes `"0.8.0"`.
- An unversioned manual: count releases in the discord channel and use `"0.0.X"`. If discord search fails you, `"0.0.1"` is fine; bump on update.

### Source: `url` vs `local`

Two source types per version. Prefer `url` to keep the repo small.

- **`url`** — direct download link to the .apworld file (typically a GitHub release artifact):
  ```toml
  "0.1.0" = { url = "https://github.com/foo/bar/releases/download/0.1.0/foo.apworld" }
  ```
- **`local`** — the .apworld is committed to `apworlds/` as `{apworld}-{version}.apworld`. Use this when the artifact only lives somewhere unstable (e.g., a Discord pinned message):
  ```toml
  "0.1.0" = { local = "../apworlds/foo-0.1.0.apworld" }
  ```

### `default_url` (preferred for semver-tagged GitHub releases)

When release tags are semver-compatible, set a top-level `default_url` template and leave the per-version objects empty:

```toml
default_url = "https://github.com/foo/bar/releases/download/{{version}}/foo.apworld"

[versions]
"0.1.0" = {}
"0.2.0" = {}
```

This makes updates a one-line change and lets tooling auto-fetch new releases.

## Inclusion criteria

The criteria for what gets indexed are set by the upstream maintainer. Summarised from the upstream README:

- The apworld must not be banned on the Archipelago server for copyright reasons.
- It must not contain large opaque executable binary blobs or depend on any.
- It must not have obvious flaws that break large multiworld generation: direct `random` usage, broken logic, problematic test failures, etc.
- It must not make use of a remote resource during generation.
- It must not require a ROM to generate. Already-indexed worlds are grandfathered; new ROM-dependent worlds are not accepted.
- The generation failure rate from [Eijebong's fuzzer](https://github.com/Eijebong/Archipelago-fuzzer) must be below 1% (excluding `OptionError`s). Failures before `generate_basic` are typically excused since they're caught by YAML validation.
- A beta of a core verified game must use a distinct world name (e.g., `LADX` → `LADX beta`).

> [!IMPORTANT]
> Do **NOT** demand that an APWorld author cater their package to be included in the index. The index follows authors, not the other way around.

## What this fork adds on top

Two additive layers on top of the upstream index:

### 1. Security-audit pipeline

- A separate audit pipeline (in progress) runs against every PR that touches `index/*.toml`.
- The auditor downloads each newly-added APWorld version, sandboxes it in a container with no network and no host access, extracts only the Python source, and feeds it to an LLM for a structured security review.
- A verdict (`PASS` / `NEEDS_REVIEW` / `FAIL`) is posted as a PR comment.

### 2. Empirical fuzz verdicts (`[[fuzz_results]]`)

A top-level array-of-tables records empirical fuzz outcomes per (version, run). Optional and additive: TOMLs without it parse identically; tools that do not care can ignore it.

```toml
[[fuzz_results]]
version = "0.7.0"
verdict = "clean"           # "clean" | "flaky" | "broken"
fuzzed_at = "2026-05-13"    # ISO date, used for ordering
seeds = 5000
default_rate = 0.004        # decimal (multiply by 100 for display)
worst_hook = "default"
worst_hook_rate = 0.004
ap_version = "0.6.2"        # optional; AP core version the fuzz ran against
hook_suite_sha = "abcdef0"  # optional; git short-sha of the hook suite used
fuzz_py_sha = "1234567"     # optional; fuzz.py revision used
```

Schema rules:

- **Top-level only.** Records live at the document root, not under `[versions]`. The `[versions]` table stays byte-for-byte upstream-compatible.
- **Multi-result support.** A version may have multiple records (re-fuzz over time, different AP versions, different hook suites). Downstream readers typically pick the most recent by `fuzzed_at`.
- **Strict TOML parse.** A CI lint runs `python -m tomllib` (stdlib) over every `index/*.toml` on PR. Any file that fails to parse fails the check.

Verdict thresholds (carried over from the prior schema; reflect the bananium 10-hook suite as of 2026-05-13):

- `clean` -- default-hook fail rate < 1% AND every other hook < 3%.
- `flaky` -- default < 3% OR a non-default hook in the 3-10% band.
- `broken` -- default >= 3% OR a critical hook >= 10%.

The first cut of this schema (PR #113) nested the record under `[versions."<v>".fuzz_result]`. That shape conflicted with the inline `"<v>" = {}` declaration on the same key under TOML spec rules and was silently unparseable in stdlib `tomllib`. The current top-level shape replaces it. See `Tools/migrate-fuzz-result-to-flat.py` for the one-shot migration that ran when the schema flipped.

This is purely additive -- no existing upstream rule changes. See [`SECURITY.md`](./SECURITY.md) for the verdict semantics, threat model, and how to report a vulnerability.
