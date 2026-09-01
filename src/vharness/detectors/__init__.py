"""Detector stage: judges generations. Built-ins register on import."""

from .base import Detector, register_builtin  # noqa: F401
from . import json_verdict  # noqa: F401
