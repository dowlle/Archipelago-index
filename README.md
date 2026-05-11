# Archipelago-index (dowlle fork)

A downstream fork of [mooinglemur/Archipelago-index](https://github.com/mooinglemur/Archipelago-index), the community-curated index of Archipelago Multiworld APWorld releases. This fork exists to:

1. **Sync from the MooingLemur upstream**, so a personal copy stays current without depending on anyone's downtime.
2. **Run an automated source-level security audit** on every APWorld update that lands here, via [`dowlle/apworld-auditor`](https://github.com/dowlle/apworld-auditor). The audit verdict is posted on each PR. See [`SECURITY.md`](./SECURITY.md) for the audit policy.

## Where to request new APWorlds

> [!IMPORTANT]
> **Open community contributions go to the upstream:** [mooinglemur/Archipelago-index](https://github.com/mooinglemur/Archipelago-index).
> Open your PR there. Dowlle syncs MooingLemur's `main` into this fork.

PRs opened directly here are welcome but the same change will need to land upstream to reach the wider ecosystem. See [`CONTRIBUTING.md`](./CONTRIBUTING.md) for more.

## TOML schema (for reference)

The index format is unchanged from upstream. A world entry lives at `index/{apworld}.toml` and looks like this:

```toml
name = "A Link to the Past"        # required; must match the world name used in YAML
display_name = "ALttP"             # optional; pretty name when `name` is ugly (e.g., "Manual_Foo_Bar")
home = "https://discord.com/..."   # optional; discord thread, github repo, or other canonical URL
tags = ["ad"]                      # optional; "ad" = after-dark server

[versions]
"0.1.0" = { url = "https://github.com/foo/bar/releases/download/0.1.0/foo.apworld" }
"0.2.0" = { local = "../apworlds/foo-0.2.0.apworld" }
```

Filename rule: `{apworld}.toml` MUST match the apworld name. For "A Link to the Past" with apworld `alttp`, the file is `alttp.toml`.

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

The only difference from MooingLemur's upstream is the security-audit layer:

- A GitHub Actions / Atlas-runner pipeline (in progress) runs `apworld-auditor` against every PR that touches `index/*.toml`.
- The auditor downloads each newly-added APWorld version, sandboxes it in a Docker container with no network and no host access, extracts only the Python source, and feeds it to Claude Code for a structured security review.
- A verdict (`PASS` / `NEEDS_REVIEW` / `FAIL`) is posted as a PR comment.

This is purely additive — no existing upstream rule changes. See [`SECURITY.md`](./SECURITY.md) for the verdict semantics, threat model, and how to report a vulnerability.
