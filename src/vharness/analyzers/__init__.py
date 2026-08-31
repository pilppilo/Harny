"""Analyzer registry — importing submodules registers them."""

from .base import Analyzer, Chunk, get_analyzer_for, register, all_analyzers  # noqa: F401

# Import for registration side effects.
from . import ccpp  # noqa: F401
from . import web  # noqa: F401
from . import shell  # noqa: F401
from . import distroconf  # noqa: F401
