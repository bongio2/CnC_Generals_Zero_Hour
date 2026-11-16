#!/usr/bin/env python3
"""Verify that a supplied invalid save is rejected without crashing.

Usage: python3 scripts/qa/test-save-load-rejection.py
       --launcher PATH --save PATH --log NEW_LOG_PATH
The launcher must accept -win -loadsave FILE and configure the game's runtime.
Only a temporary copy of the supplied save is passed to the game.
"""

import argparse
import hashlib
import os
from pathlib import Path
import shutil
import signal
import subprocess
import tempfile


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--launcher", required=True, type=Path)
    parser.add_argument("--save", required=True, type=Path)
    parser.add_argument("--log", required=True, type=Path)
    parser.add_argument("--timeout", type=float, default=90)
    args = parser.parse_args()
    launcher = args.launcher.resolve(strict=True)
    save = args.save.resolve(strict=True)
    log = args.log.resolve()
    if args.timeout <= 0:
        parser.error("--timeout must be positive")
    if log in (save, launcher):
        parser.error("--log must not overwrite the save or launcher")

    digest = hashlib.sha256(save.read_bytes()).digest()
    log.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="generalsx-save-rejection-") as directory:
        copied_save = Path(directory) / save.name
        shutil.copy2(save, copied_save)
        with log.open("xb") as output:
            process = subprocess.Popen(
                [str(launcher), "-win", "-loadsave", str(copied_save)],
                cwd=launcher.parent,
                stdout=output,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            try:
                returncode = process.wait(timeout=args.timeout)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()
                print(f"FAIL: save rejection timed out; see {log}")
                return 1

    if hashlib.sha256(save.read_bytes()).digest() != digest:
        print("FAIL: supplied save changed during testing")
        return 1
    text = log.read_text(errors="replace")
    if returncode != 0:
        print(f"FAIL: game exited with code {returncode}; see {log}")
        return 1
    if "Failed to load save game '" not in text:
        print(f"FAIL: explicit save rejection was not observed; see {log}")
        return 1
    if any(message in text.lower() for message in ("segmentation fault", "bad sleepy idx")):
        print(f"FAIL: cleanup crash diagnostics found; see {log}")
        return 1
    print(f"PASS: copied save rejected cleanly; original unchanged; log: {log}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
