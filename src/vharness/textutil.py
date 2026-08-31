"""Text utilities: markdown-fence stripping and balanced JSON extraction."""

from __future__ import annotations

import re

_FENCE_RE = re.compile(r"^```[a-zA-Z0-9_-]*\s*|\s*```$")


def strip_code_fences(text: str) -> str:
    """Strip leading/trailing markdown code fences from all lines."""
    lines = text.strip().splitlines()
    if lines and lines[0].lstrip().startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()


def extract_json_block(text: str) -> str | None:
    """Return the first balanced top-level ``{...}`` block, string/escape aware.

    Handles model output that has stray prose around the JSON object.
    """
    start = text.find("{")
    while start != -1:
        depth = 0
        in_str = False
        escaped = False
        for i in range(start, len(text)):
            ch = text[i]
            if in_str:
                if escaped:
                    escaped = False
                elif ch == "\\":
                    escaped = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return text[start : i + 1]
        start = text.find("{", start + 1)
    return None


def mask_ranges(text: str) -> list[tuple[int, int]]:
    """Ranges (start, end) of comments and string/char literals in C-like code.

    Used by chunkers so brace/paren matching ignores braces inside strings
    and comments. Overlapping constructs are resolved in lexical order.
    """
    ranges: list[tuple[int, int]] = []
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        two = text[i : i + 2]
        if two == "//":
            j = text.find("\n", i)
            j = n if j == -1 else j
            ranges.append((i, j))
            i = j
        elif two == "/*":
            j = text.find("*/", i + 2)
            j = n if j == -1 else j + 2
            ranges.append((i, j))
            i = j
        elif ch in "\"'":
            quote = ch
            j = i + 1
            while j < n:
                if text[j] == "\\":
                    j += 2
                    continue
                if text[j] == quote:
                    break
                j += 1
            ranges.append((i, min(j + 1, n)))
            i = j + 1
        else:
            i += 1
    return ranges


def mask_positions(text: str) -> set[int]:
    """Set of positions inside comments/strings (see mask_ranges)."""
    masked: set[int] = set()
    for start, end in mask_ranges(text):
        masked.update(range(start, end))
    return masked
