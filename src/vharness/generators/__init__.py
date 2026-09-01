"""Generator stage: model I/O. Built-ins register on import."""

from .base import Generator, register_builtin  # noqa: F401
from . import mock  # noqa: F401

try:
    from . import openai_compat  # noqa: F401
except ModuleNotFoundError as e:  # tolerate a missing `openai` package only
    if e.name != "openai":
        raise
