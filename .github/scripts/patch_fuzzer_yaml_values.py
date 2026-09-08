#!/usr/bin/env python3
"""Teach the pinned AP fuzzer to emit YAML-safe option defaults.

Some APWorld options use Enum/StrEnum values (including inside containers).
PyYAML's SafeDumper does not represent those subclasses automatically, so the
fuzzer can abort while constructing input YAML before it runs a single seed.
The upstream fuzzer is SHA-pinned and downloaded at workflow runtime; patch its
small sanitize helper fail-closed so the normalization remains reviewable.
"""

from __future__ import annotations

import sys
from pathlib import Path


OLD = '''    def sanitize(value):
        if isinstance(value, frozenset):
            return list(value)
        return value
'''

NEW = '''    def sanitize(value):
        if isinstance(value, Enum):
            return sanitize(value.value)
        if isinstance(value, dict):
            return {sanitize(key): sanitize(item) for key, item in value.items()}
        if isinstance(value, (list, tuple, set, frozenset)):
            return [sanitize(item) for item in value]
        return value
'''


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit(f"usage: {Path(sys.argv[0]).name} PATH/TO/fuzz.py")

    target = Path(sys.argv[1])
    source = target.read_text(encoding="utf-8")
    matches = source.count(OLD)
    if matches != 1:
        raise SystemExit(
            f"refusing to patch {target}: expected one sanitize helper, found {matches}"
        )

    target.write_text(source.replace(OLD, NEW), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
