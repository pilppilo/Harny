"""Typed contracts for agent actions and tool execution.

Tools are deliberately separate from the planner: an LLM may propose an
action, but only a registered executor should perform it.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class ToolAction:
    """A planner-produced request for one tool invocation."""

    tool: str
    target: str
    parameters: dict[str, Any] = field(default_factory=dict)
    purpose: str = ""
    action_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])

    @property
    def fingerprint(self) -> str:
        payload = {"tool": self.tool, "target": self.target,
                   "parameters": self.parameters}
        return hashlib.sha256(json.dumps(payload, sort_keys=True,
                                          separators=(",", ":"),
                                          default=str).encode()).hexdigest()


@dataclass(frozen=True)
class ToolResult:
    """Normalized, bounded output from a tool executor."""

    action_id: str
    status: str  # ok | rejected | timeout | error
    output: Any = None
    error: str | None = None
    evidence: list[str] = field(default_factory=list)


class Tool(Protocol):
    name: str

    def execute(self, action: ToolAction) -> ToolResult:
        ...


class ToolRegistry:
    """Registry for explicitly available assessment tools."""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> Tool:
        if not getattr(tool, "name", None):
            raise ValueError("tool must define a name")
        if tool.name in self._tools:
            raise ValueError(f"duplicate tool name: {tool.name!r}")
        self._tools[tool.name] = tool
        return tool

    def get(self, name: str) -> Tool:
        try:
            return self._tools[name]
        except KeyError:
            raise KeyError(f"unknown tool {name!r}; known: {sorted(self._tools)}") from None

    def names(self) -> list[str]:
        return sorted(self._tools)


TOOLS = ToolRegistry()
