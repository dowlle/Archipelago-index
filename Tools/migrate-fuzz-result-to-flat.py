#!/usr/bin/env python3
"""Migrate per-version `[versions."X.Y.Z".fuzz_result]` sub-tables to flat
top-level `[[fuzz_results]]` array-of-tables with `version` as a field.

Why this exists:

PR #113's original shape declared both an inline `"X.Y.Z" = {}` (or
`"X.Y.Z" = { url = "..." }`) in `[versions]` AND a `[versions."X.Y.Z".fuzz_result]`
sub-table on the same key. That violates the TOML spec -- the inline form
fully declares the table at that key, and the sub-table header then tries
to redeclare it. Stdlib `tomllib` (and most spec-compliant parsers) reject
this as a duplicate declaration. Downstream consumers using `tomllib`
silently drop those TOMLs from the index.

This script rewrites every nested `[versions."X.Y.Z".fuzz_result]` block as
a top-level `[[fuzz_results]]` entry with `version = "X.Y.Z"` added. The
`[versions]` table is preserved byte-for-byte (the inline lines stay, with
their `url` / `local` payloads intact), so the schema remains compatible
with upstream forks that don't carry fuzz data.

Design notes:

- Text manipulation, not tomlkit round-tripping. Round-tripping is what bit
  PR #113 in the first place.
- `tomllib.load()` validation on every rewritten file before writing back
  to disk. If the rewrite produces unparseable TOML, abort that file and
  leave it untouched.
- Idempotent: if a file already has top-level `[[fuzz_results]]` and no
  nested `.fuzz_result` blocks, it's a no-op.
- `--dry-run` prints planned changes without writing.
"""

from __future__ import annotations

import argparse
import io
import pathlib
import re
import sys
import tomllib
from typing import Optional


# Matches headers like:
#   [versions."0.7.0".fuzz_result]
#   [versions."CrystalProject-v0.15.1".fuzz_result]
#   [versions."beta3.3".fuzz_result]
NESTED_HEADER_RE = re.compile(
    r'^\[versions\."([^"]+)"\.fuzz_result\]\s*$', re.MULTILINE
)

# Matches bare per-version sub-table headers like `[versions."0.7.0"]`. These
# are not the fuzz_result headers; they declare a per-version sub-table that
# carries `url` / `local` keys. They are rare in the corpus (one file at
# migration time) and conflict with an empty inline `"0.7.0" = {}` declaration
# above. Where both exist, the migration drops the empty inline so the header
# form is the sole declaration.
BARE_VERSION_HEADER_RE = re.compile(
    r'^\[versions\."([^"]+)"\]\s*$', re.MULTILINE
)

# Matches top-level [[fuzz_results]] blocks (used for idempotency check only).
TOP_LEVEL_RE = re.compile(r'^\[\[fuzz_results\]\]\s*$', re.MULTILINE)


def find_bare_version_subtables(text: str) -> set[str]:
    """Return the set of versions declared by bare `[versions."X.Y.Z"]`
    sub-table headers (not the `.fuzz_result` variant)."""
    found = set()
    for line in text.split("\n"):
        m = BARE_VERSION_HEADER_RE.match(line)
        if m:
            found.add(m.group(1))
    return found


def drop_redundant_inline_for_subtabled_versions(text: str, versions: set[str]) -> str:
    """For each version `V` declared by a bare `[versions."V"]` header
    elsewhere in the file, drop the redundant empty inline `"V" = {}` line
    inside the `[versions]` table. The header form takes over as the
    declaration. Only acts on EMPTY inlines (`= {}`); non-empty inlines
    `= { url = "..." }` are an actual schema conflict the script does not
    silently resolve.
    """
    if not versions:
        return text
    lines = text.split("\n")
    out: list[str] = []
    for line in lines:
        m = re.match(r'^"([^"]+)"\s*=\s*\{\s*\}\s*$', line.strip())
        if m and m.group(1) in versions:
            # Drop this line entirely.
            continue
        out.append(line)
    return "\n".join(out)


def find_block_end(lines: list[str], start: int) -> int:
    """Return the index AFTER the last line of a TOML block starting at `start`.

    A block ends at:
      - the next `[...]` or `[[...]]` header line, or
      - a blank line followed by EOF, or
      - end of file.
    """
    i = start + 1
    while i < len(lines):
        line = lines[i].rstrip("\r\n")
        # A new header starts a new block.
        if line.startswith("[") and (line.endswith("]")):
            return i
        i += 1
    return i


def extract_fuzz_blocks(text: str) -> list[tuple[str, dict]]:
    """Find every `[versions."X.Y.Z".fuzz_result]` block and return its
    (version, fields dict) pairs.

    Uses tomllib to parse the FIELDS via a synthesized minimal TOML snippet
    so we get correct type handling (floats, strings, ints, dates as ISO
    strings). The block's raw key-value lines are extracted from the source
    text between the header and the next block boundary.
    """
    results: list[tuple[str, dict]] = []
    lines = text.split("\n")
    for i, line in enumerate(lines):
        m = NESTED_HEADER_RE.match(line)
        if not m:
            continue
        version = m.group(1)
        end = find_block_end(lines, i)
        body_lines = lines[i + 1:end]
        # Strip trailing blank lines so the synthesized TOML parses cleanly.
        while body_lines and body_lines[-1].strip() == "":
            body_lines.pop()
        body = "\n".join(body_lines)
        # Synthesize a minimal TOML to parse just these fields.
        snippet = "[__tmp__]\n" + body + "\n"
        try:
            parsed = tomllib.loads(snippet)
            fields = parsed.get("__tmp__", {})
            results.append((version, fields))
        except tomllib.TOMLDecodeError as e:
            print(f"  WARN: could not parse fields under [versions.\"{version}\".fuzz_result]: {e}", file=sys.stderr)
            continue
    return results


def remove_nested_blocks(text: str) -> str:
    """Remove every `[versions."X.Y.Z".fuzz_result]` header + body from the
    source text. Leaves a single blank line where each block stood so the
    result doesn't accumulate trailing whitespace.
    """
    lines = text.split("\n")
    out: list[str] = []
    skip_until: Optional[int] = None
    i = 0
    while i < len(lines):
        line = lines[i]
        m = NESTED_HEADER_RE.match(line)
        if m:
            end = find_block_end(lines, i)
            # Trim a trailing blank line attached to this block, so the
            # surrounding spacing stays sane.
            if end < len(lines) and lines[end - 1].strip() == "":
                # already handled below
                pass
            i = end
            continue
        out.append(line)
        i += 1
    # Collapse runs of >2 blank lines into a single blank line.
    cleaned: list[str] = []
    blank_run = 0
    for line in out:
        if line.strip() == "":
            blank_run += 1
            if blank_run <= 1:
                cleaned.append(line)
        else:
            blank_run = 0
            cleaned.append(line)
    # Strip trailing blank lines so the file ends with a single newline.
    while cleaned and cleaned[-1].strip() == "":
        cleaned.pop()
    return "\n".join(cleaned) + "\n"


def emit_top_level_block(version: str, fields: dict) -> str:
    """Render one `[[fuzz_results]]` block. Field order is fixed for
    diff stability across files.
    """
    # Canonical field order: version first, verdict/dates next, then rates.
    ordered_keys = [
        "version",
        "verdict",
        "fuzzed_at",
        "seeds",
        "ap_version",
        "hook_suite_sha",
        "fuzz_py_sha",
        "default_rate",
        "worst_hook",
        "worst_hook_rate",
    ]
    record = {"version": version, **fields}
    out = io.StringIO()
    out.write("[[fuzz_results]]\n")
    for k in ordered_keys:
        if k not in record:
            continue
        v = record[k]
        out.write(f"{k} = {format_value(v)}\n")
    # Any unexpected extra keys go at the end so we don't silently drop data.
    for k, v in record.items():
        if k in ordered_keys:
            continue
        out.write(f"{k} = {format_value(v)}\n")
    return out.getvalue()


def format_value(v) -> str:
    """Render a Python value as a TOML literal."""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        # Preserve precision; tomllib gives us full float values.
        s = repr(v)
        # repr can emit e.g. '0.322923'; that's fine.
        return s
    if isinstance(v, str):
        # Escape backslashes and quotes; index data should not contain these
        # but be defensive.
        escaped = v.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    # Lists, dates, etc. -- fall back to repr (no current callers).
    return repr(v)


def migrate_file(path: pathlib.Path, dry_run: bool) -> tuple[str, int]:
    """Return (status, n_blocks_moved). status is one of:
      - "ok"       -- migration applied (or would be applied in --dry-run)
      - "skip"     -- no nested blocks; no-op
      - "fail"     -- rewrite did not parse; file left untouched
    """
    original = path.read_text(encoding="utf-8")

    blocks = extract_fuzz_blocks(original)
    if not blocks:
        return ("skip", 0)

    # Build new text: strip nested fuzz_result blocks, drop redundant empty
    # inlines for versions also declared via bare `[versions."X"]` headers,
    # then append top-level [[fuzz_results]] blocks.
    cleaned = remove_nested_blocks(original)
    subtabled_versions = find_bare_version_subtables(cleaned)
    cleaned = drop_redundant_inline_for_subtabled_versions(cleaned, subtabled_versions)
    appended_parts = [cleaned.rstrip("\n")]
    appended_parts.append("")  # one blank line separator
    for version, fields in blocks:
        appended_parts.append(emit_top_level_block(version, fields).rstrip("\n"))
        appended_parts.append("")  # blank line between records
    # Drop trailing extra blank, keep one trailing newline.
    while appended_parts and appended_parts[-1] == "":
        appended_parts.pop()
    new_text = "\n".join(appended_parts) + "\n"

    # Validate.
    try:
        tomllib.loads(new_text)
    except tomllib.TOMLDecodeError as e:
        print(f"  FAIL {path.name}: rewritten text does not parse: {e}", file=sys.stderr)
        return ("fail", 0)

    if dry_run:
        return ("ok", len(blocks))

    path.write_text(new_text, encoding="utf-8")
    return ("ok", len(blocks))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--index-dir",
        default="index",
        help="Path to the index/ directory (default: index)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would change without writing files.",
    )
    parser.add_argument(
        "--show",
        metavar="FILENAME",
        help="Print the rewritten text for the given file and exit (no write).",
    )
    args = parser.parse_args()

    index_dir = pathlib.Path(args.index_dir)
    if not index_dir.is_dir():
        print(f"ERROR: {index_dir} is not a directory", file=sys.stderr)
        return 2

    if args.show:
        target = index_dir / args.show
        original = target.read_text(encoding="utf-8")
        blocks = extract_fuzz_blocks(original)
        if not blocks:
            print(f"# {args.show}: no nested fuzz_result blocks; would be unchanged.")
            return 0
        cleaned = remove_nested_blocks(original)
        subtabled = find_bare_version_subtables(cleaned)
        cleaned = drop_redundant_inline_for_subtabled_versions(cleaned, subtabled)
        parts = [cleaned.rstrip("\n"), ""]
        for version, fields in blocks:
            parts.append(emit_top_level_block(version, fields).rstrip("\n"))
            parts.append("")
        while parts and parts[-1] == "":
            parts.pop()
        new_text = "\n".join(parts) + "\n"
        print(new_text, end="")
        return 0

    n_files = 0
    n_skipped = 0
    n_failed = 0
    n_blocks = 0
    failed_files: list[str] = []
    changed_files: list[str] = []

    for path in sorted(index_dir.glob("*.toml")):
        status, count = migrate_file(path, args.dry_run)
        if status == "ok":
            n_files += 1
            n_blocks += count
            changed_files.append(path.name)
        elif status == "skip":
            n_skipped += 1
        elif status == "fail":
            n_failed += 1
            failed_files.append(path.name)

    verb = "WOULD migrate" if args.dry_run else "Migrated"
    print(f"{verb} {n_files} file(s), {n_blocks} block(s) moved.")
    print(f"Skipped {n_skipped} file(s) with no nested fuzz_result blocks.")
    if n_failed:
        print(f"FAIL: {n_failed} file(s) could not be safely rewritten:", file=sys.stderr)
        for name in failed_files:
            print(f"  {name}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
