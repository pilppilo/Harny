"""Canonical JSON conversion at durable and external boundaries."""

# pylint: disable=too-many-return-statements
# Each JSON shape has one direct conversion branch at this narrow boundary.

from __future__ import annotations

import json
import math
from dataclasses import fields, is_dataclass
from decimal import Decimal
from enum import Enum
from typing import Mapping

from .errors import ContractError
from .models import JsonValue


def to_json_value(value: object) -> JsonValue:
    """Convert supported immutable domain data into JSON-compatible values."""
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ContractError("JSON values must be finite")
        return value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Enum):
        return to_json_value(value.value)
    if is_dataclass(value):
        return {
            item.name: to_json_value(getattr(value, item.name))
            for item in fields(value)
        }
    if isinstance(value, Mapping):
        if not all(isinstance(key, str) for key in value):
            raise ContractError("JSON object keys must be strings")
        return {key: to_json_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return tuple(to_json_value(item) for item in value)
    raise ContractError(f"unsupported JSON value type: {type(value).__name__}")


def canonical_json(value: object) -> str:
    """Produce stable UTF-8 JSON used for durable payloads and content hashing."""
    return json.dumps(
        to_json_value(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def parse_json_object(raw: str | bytes) -> Mapping[str, JsonValue]:
    """Parse one external JSON object and reject non-object/non-finite input."""
    try:
        value = json.loads(raw, parse_constant=_reject_constant)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ContractError(f"invalid JSON object: {exc}") from exc
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ContractError("expected a JSON object")
    return value


def _reject_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant {value!r}")
