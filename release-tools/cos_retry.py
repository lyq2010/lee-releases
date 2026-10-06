#!/usr/bin/env python3
"""Run one COS mirror command. Kill it after 180s and retry."""

from __future__ import annotations

import subprocess
import sys

ATTEMPTS = 3
TIMEOUT_SECONDS = 180


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit("usage: cos_retry.py COMMAND [ARGS...]")
    command = sys.argv[1:]
    for attempt in range(1, ATTEMPTS + 1):
        print(
            f"COS attempt {attempt}/{ATTEMPTS} (timeout {TIMEOUT_SECONDS}s)",
            flush=True,
        )
        try:
            result = subprocess.run(command, timeout=TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            print(
                f"COS attempt {attempt} timed out after {TIMEOUT_SECONDS}s",
                flush=True,
            )
            if attempt == ATTEMPTS:
                sys.exit(124)
            continue
        if result.returncode == 0:
            return
        print(f"COS attempt {attempt} exited {result.returncode}", flush=True)
        if attempt == ATTEMPTS:
            sys.exit(result.returncode)


if __name__ == "__main__":
    main()
