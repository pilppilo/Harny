"""Central logging for vharness.

Library modules log via ``log.info/warning/...``; the CLI configures the
handler once (``setup``). Default level is WARNING so embedded use (Inspect
adapter, notebooks, tests) stays silent unless asked.

Verbosity mapping: -v → INFO (operational chatter, per-attempt progress),
-vv → DEBUG (worker internals, cache decisions, plugin loads).
"""

from __future__ import annotations

import logging

_LOG = logging.getLogger("vharness")
_VERBOSITY: int = 0


class _CompactFormatter(logging.Formatter):
    """Single-letter level + message: `I endpoint: http://… model=qwen…`."""

    _ABBREV = {
        logging.DEBUG: "D",
        logging.INFO: "I",
        logging.WARNING: "W",
        logging.ERROR: "E",
        logging.CRITICAL: "C",
    }

    def format(self, record: logging.LogRecord) -> str:
        level = self._ABBREV.get(record.levelno, "?")
        msg = record.getMessage()
        if record.exc_info:
            msg += "\n" + self.formatException(record.exc_info)
        return f"{level} {msg}"


def setup(verbosity: int = 0, quiet: bool = False) -> None:
    """Configure the root vharness logger. Idempotent (replaces handlers)."""
    global _VERBOSITY
    _VERBOSITY = -1 if quiet else verbosity
    if quiet:
        level = logging.CRITICAL
    elif verbosity >= 2:
        level = logging.DEBUG
    else:
        level = logging.INFO
    handler = logging.StreamHandler()
    handler.setFormatter(_CompactFormatter())
    _LOG.handlers.clear()
    _LOG.addHandler(handler)
    _LOG.setLevel(level)


def get_verbosity() -> int:
    """Return the currently configured verbosity level (0=normal, 1=verbose, 2=debug, -1=quiet)."""
    return _VERBOSITY


def get(name: str) -> logging.Logger:
    """Child logger for a module (e.g. ``log.get(__name__)``)."""
    return logging.getLogger(name)


log = _LOG
