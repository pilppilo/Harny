#!/usr/bin/env python3
"""Backwards-compatible shim: harny.py --dir <src> --out report.sarif

Delegates to the vharness CLI (`scan` preset). Works with the project venv
(`uv run python harny.py …`) or a bare interpreter from a checkout
(`python3 harny.py …` — dry-run needs no third-party packages).
"""

from __future__ import annotations

import sys
from pathlib import Path

# Bootstrap the in-repo package when run with a bare interpreter (no venv
# activated, vharness not pip-installed).
_SRC = Path(__file__).resolve().parent / "src"
if (_SRC / "vharness").is_dir():
    sys.path.insert(0, str(_SRC))

from vharness.cli import main  # noqa: E402

if __name__ == "__main__":
    args = sys.argv[1:]
    mapped: list[str] = ["scan"]
    it = iter(args)
    for a in it:
        if a == "--dir":
            mapped.append(next(it))
        elif a == "--out":
            mapped += ["--out", next(it)]
        else:
            mapped.append(a)
    sys.exit(main(mapped))
