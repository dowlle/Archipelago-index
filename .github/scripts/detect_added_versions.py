#!/usr/bin/env python3
"""Detect APWorld version additions in a PR and emit a fuzz matrix.

Reads BASE_SHA / HEAD_SHA from env, fetches `index.lock` at both
revisions, parses both as TOML, and surfaces any (apworld, version)
pair present at HEAD but not at BASE. For each, reads the matching
`index/<apworld>.toml` at HEAD to resolve the download URL
(`default_url` interpolation, per-version `url` override, or `local`
in-repo path). Produces a single GHA matrix with one entry per
(apworld, version, check) combination.

Output: writes to $GITHUB_OUTPUT
  - matrix: JSON object {"include": [...]}
  - has_targets: "true"|"false"

The matrix dimension is intentionally flat so the fuzz job can name
its 10 hook checks once and multiply across whatever (apworld, version)
pairs a PR adds. GHA caps a matrix at 256 entries; a 23-batch sweep
(23 x 10 = 230) still fits.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tomllib
from pathlib import Path

# Bananium-style 10-check suite. Identical names + run counts to the
# worker-host run-fuzz.sh so the GHA verdict semantics match locally.
CHECKS = [
    {"name": "default",                     "runs": 5000, "hook": ""},
    {"name": "no-restrictive-starts",       "runs": 5000, "hook": "hooks.no_rs:Hook"},
    {"name": "check-determinism",            "runs": 500, "hook": "hooks.determinism:Hook"},
    {"name": "check-collect-accessibility",  "runs": 500, "hook": "hooks.collect_accessibility_test:Hook"},
    {"name": "check-item-location-count",    "runs": 500, "hook": "hooks.item_location_count:Hook"},
    {"name": "check-placement-refs",         "runs": 500, "hook": "hooks.check_placement_item_location_references:Hook"},
    {"name": "check-lambda-capture",         "runs": 500, "hook": "hooks.detect_rule_variable_capture_issues:Hook"},
    {"name": "check-static-output",          "runs": 500, "hook": "hooks.detect_output_placement_changes:Hook"},
    {"name": "check-indirect-conditions",    "runs": 500, "hook": "hooks.indirect_conditions:Hook"},
    {"name": "check-ut",                     "runs": 500, "hook": "hooks.with_empty:Hook"},
]


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], text=True)


def git_show(ref: str, path: str) -> str | None:
    try:
        return git("show", f"{ref}:{path}")
    except subprocess.CalledProcessError:
        return None


def parse_lock(text: str | None) -> dict[str, set[str]]:
    """Parse an index.lock body into {apworld: {versions...}}."""
    if not text:
        return {}
    data = tomllib.loads(text)
    out: dict[str, set[str]] = {}
    for apworld, versions in data.items():
        if isinstance(versions, dict):
            out[apworld] = set(versions.keys())
    return out


def added_pairs(base_lock: dict[str, set[str]], head_lock: dict[str, set[str]]) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for apworld, versions in head_lock.items():
        base_versions = base_lock.get(apworld, set())
        for v in sorted(versions - base_versions):
            pairs.append((apworld, v))
    return pairs


def lookup_sha(head_lock_text: str, apworld: str, version: str) -> str:
    """Re-parse head lock for the sha256 of a specific entry."""
    data = tomllib.loads(head_lock_text)
    section = data.get(apworld, {})
    return section.get(version, "") if isinstance(section, dict) else ""


def resolve_source(apworld: str, version: str, repo_root: Path) -> tuple[str | None, str | None]:
    """Return (url, local_relpath). Exactly one will be set unless the entry
    is malformed (both None means skip this target with a warning)."""
    toml_path = repo_root / "index" / f"{apworld}.toml"
    if not toml_path.exists():
        print(f"::warning::No index/{apworld}.toml found at HEAD; skipping {apworld} {version}", file=sys.stderr)
        return None, None

    data = tomllib.loads(toml_path.read_text(encoding="utf-8"))
    versions = data.get("versions") or {}
    entry = versions.get(version)
    if entry is None:
        print(f"::warning::index/{apworld}.toml has no [versions].\"{version}\" entry; skipping", file=sys.stderr)
        return None, None

    if not isinstance(entry, dict):
        entry = {}

    if "local" in entry:
        return None, entry["local"]
    if "url" in entry:
        return entry["url"], None

    default_url = data.get("default_url")
    if not default_url:
        print(f"::warning::{apworld} {version} has neither url nor local nor default_url; skipping", file=sys.stderr)
        return None, None

    return default_url.replace("{{version}}", version), None


def write_outputs(matrix_json: str, has_targets: str) -> None:
    gh_output = os.environ.get("GITHUB_OUTPUT")
    if gh_output:
        with open(gh_output, "a", encoding="utf-8") as f:
            f.write(f"matrix={matrix_json}\n")
            f.write(f"has_targets={has_targets}\n")
    else:
        print(matrix_json)
        print(f"has_targets={has_targets}")


def main() -> int:
    base = os.environ["BASE_SHA"]
    head = os.environ["HEAD_SHA"]
    repo_root = Path(".").resolve()

    head_lock_text = git_show(head, "index.lock") or ""
    base_lock_text = git_show(base, "index.lock") or ""

    head_lock = parse_lock(head_lock_text)
    base_lock = parse_lock(base_lock_text)

    pairs = added_pairs(base_lock, head_lock)

    targets: list[dict] = []
    for apworld, version in pairs:
        url, local = resolve_source(apworld, version, repo_root)
        if url is None and local is None:
            continue
        targets.append({
            "apworld": apworld,
            "version": version,
            "sha256": lookup_sha(head_lock_text, apworld, version),
            "url": url or "",
            "local": local or "",
        })

    include: list[dict] = []
    for t in targets:
        for c in CHECKS:
            include.append({
                **t,
                "check_name": c["name"],
                "check_runs": c["runs"],
                "check_hook": c["hook"],
            })

    print(f"Detected {len(targets)} target(s), {len(include)} matrix job(s):", file=sys.stderr)
    for t in targets:
        src = t["url"] if t["url"] else f"local:{t['local']}"
        print(f"  - {t['apworld']} {t['version']} ({src})", file=sys.stderr)

    if include:
        matrix_json = json.dumps({"include": include})
        has_targets = "true"
    else:
        # GHA requires at least one matrix entry; the noop never runs
        # because the fuzz job's `if: has_targets == 'true'` skips it.
        matrix_json = json.dumps({"include": [{"apworld": "noop", "version": "noop", "sha256": "", "url": "", "local": "", "check_name": "noop", "check_runs": 0, "check_hook": ""}]})
        has_targets = "false"

    write_outputs(matrix_json, has_targets)
    return 0


if __name__ == "__main__":
    sys.exit(main())
