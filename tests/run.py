#!/usr/bin/env python3
"""Run the CraigVault suite.

    python3 tests/run.py              # everything
    python3 tests/run.py password     # only modules whose name contains "password"

Exit status is 0 only if every check passed.
"""

import importlib.util
import os
import sys
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import harness  # noqa: E402

GREEN, RED, DIM, BOLD, OFF = "\033[32m", "\033[31m", "\033[2m", "\033[1m", "\033[0m"
if not sys.stdout.isatty():
    GREEN = RED = DIM = BOLD = OFF = ""

ORDER = [
    "test_container.py",        # the property that must never regress, and the format
    "test_lock_state.py",       # issue #1
    "test_file_targets.py",     # issue #2
    "test_editor_lock.py",      # issue #3
    "test_autolock.py",         # issue #4
    "test_password_policy.py",  # issue #5
    "test_locked_ui.py",        # issue #8
    "test_download_path.py",    # issue #6
]


def load(path):
    spec = importlib.util.spec_from_file_location(
        os.path.basename(path)[:-3], os.path.join(HERE, path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    only = sys.argv[1:]
    names = [n for n in ORDER if os.path.exists(os.path.join(HERE, n))]
    missing = [n for n in ORDER if n not in names]
    if only:
        names = [n for n in names if any(f in n for f in only)]

    print("%sCraigVault%s  %s" % (BOLD, OFF, harness.INDEX))
    total_failed, started = [], time.time()

    for name in names:
        results = harness.Results()
        t0 = time.time()
        try:
            load(name).run(results)
        except Exception:
            results.check("module raised", False, traceback.format_exc().strip().splitlines()[-1])
            traceback.print_exc()
        bad = results.failed
        mark = "%s✗%s" % (RED, OFF) if bad else "%s✓%s" % (GREEN, OFF)
        print("\n%s %s %s(%d checks, %.1fs)%s" %
              (mark, name[:-3], DIM, len(results.rows), time.time() - t0, OFF))
        for label, ok, detail in results.rows:
            if ok:
                print("   %s✓%s %s" % (GREEN, OFF, label))
            else:
                print("   %s✗ %s%s%s" % (RED, label, ("  — " + detail) if detail else "", OFF))
        total_failed += bad

    if missing:
        print("\n%s(not present: %s)%s" % (DIM, ", ".join(missing), OFF))
    elapsed = time.time() - started
    if total_failed:
        print("\n%s%d check(s) FAILED%s in %.1fs" % (RED, len(total_failed), OFF, elapsed))
        return 1
    print("\n%sall checks passed%s in %.1fs" % (GREEN, OFF, elapsed))
    return 0


if __name__ == "__main__":
    sys.exit(main())
