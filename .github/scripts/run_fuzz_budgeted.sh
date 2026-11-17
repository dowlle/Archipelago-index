#!/usr/bin/env bash
# Run a fuzz.py command under a wall-clock budget without changing its run count.
#
# usage: run_fuzz_budgeted.sh BUDGET_SECONDS TARGET_RUNS -- command [args...]
#
# fuzz.py handles SIGINT as KeyboardInterrupt: it stops submitting runs, prints
# its final "Success/Failures/Timeouts/Ignored" block and exits. This wrapper
# sends SIGINT to the whole process group when the budget expires (SIGKILL
# KILL_GRACE seconds later if it hangs), then prints one machine-readable line:
#
#   PARTIAL: <done> / <target> done. <failures> failures, <timeouts> timeouts, <ignored> ignored.
#
# <done> = success + failures + timeouts + ignored, the same quantity fuzz.py's
# own "N / R done." progress lines report. If the run finishes inside the
# budget nothing is added and fuzz.py's own exit code is returned.
# On a budget stop the exit code is 0 when failures + timeouts == 0, else 1,
# mirroring fuzz.py's own exit rule, so a clean partial run stays green.
set -uo pipefail

BUDGET="${1:?budget seconds}"; TARGET="${2:?target runs}"; shift 2
[ "${1:-}" = "--" ] && shift
KILL_GRACE="${KILL_GRACE:-120}"
LOG="$(mktemp)"
trap 'rm -f "$LOG"' EXIT

timeout -s INT -k "$KILL_GRACE" "$BUDGET" "$@" 2>&1 | tee "$LOG"
rc="${PIPESTATUS[0]}"

# 124 = budget expired and the command stopped after SIGINT; 137 = needed SIGKILL.
if [ "$rc" -ne 124 ] && [ "$rc" -ne 137 ]; then
  exit "$rc"
fi

python3 - "$LOG" "$TARGET" "$rc" <<'PY'
import re, sys
log, target, rc = open(sys.argv[1], errors="replace").read(), sys.argv[2], sys.argv[3]
final = {k: re.findall(rf"^{k}: (\d+)\s*$", log, re.M) for k in ("Success", "Failures", "Timeouts", "Ignored")}
if all(final.values()):
    s, f, t, i = (int(final[k][-1]) for k in ("Success", "Failures", "Timeouts", "Ignored"))
    done = s + f + t + i
else:
    # Fall back to the last progress line (printed every runs//50 results).
    m = re.findall(r"^(\d+) / \d+ done\. (\d+) failures, (\d+) timeouts, (\d+) ignored\.", log, re.M)
    if not m:
        print(f"::error::budget expired (exit {rc}) but no fuzz progress could be parsed")
        sys.exit(1)
    done, f, t, i = (int(x) for x in m[-1])
print(f"PARTIAL: {done} / {target} done. {f} failures, {t} timeouts, {i} ignored.")
print(f"::warning::fuzz budget expired after {done} of {target} runs ({f} failures, {t} timeouts)")
sys.exit(1 if (f + t) else 0)
PY
