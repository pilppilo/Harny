"""Evaluator stage: reports and metrics. Built-ins register on import."""

from .base import Evaluator, register_builtin  # noqa: F401
from . import reports  # noqa: F401
from . import metrics  # noqa: F401
