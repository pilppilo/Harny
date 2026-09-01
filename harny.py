#!/usr/bin/env python3
"""Backwards-compatible shim: harny.py --dir <src> --out report.sarif

Delegates to the vharness CLI (`scan` preset).
"""

from __future__ import annotations

import sys

from vharness.cli import main

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
