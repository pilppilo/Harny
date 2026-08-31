"""C/C++ analyzer: brace-matched, string/comment-aware function chunking."""

from __future__ import annotations

import re

from ..textutil import mask_positions
from .base import Analyzer, Chunk, register

# File gate: strong sinks only. malloc/free/memcpy are dropped because they
# appear in nearly every C file and made the old triage useless.
STRONG_SINKS = re.compile(
    r"\b(strcpy|strcat|sprintf|vsprintf|gets|system|popen|execve|execl|execlp|execvp|"
    r"sscanf|strncpy|strncat|realpath|readlink|dlopen|wordexp|pthread_exit)\b"
)
# Chunk gate: strong + memory-safety relevant calls.
ALL_SINKS = re.compile(
    r"\b(strcpy|strcat|sprintf|vsprintf|gets|system|popen|execve|execl|execlp|execvp|"
    r"sscanf|strncpy|strncat|realpath|readlink|dlopen|wordexp|"
    r"malloc|calloc|realloc|free|memcpy|memmove|memset|alloca|"
    r"fopen|open|read|recv|scanf|atoi|strtol|getenv)\b"
)

# Candidate function-definition heads: return type, name, then '('.
_SIG_RE = re.compile(
    r"^[ \t]*(?:static\s+|inline\s+|extern\s+|const\s+|unsigned\s+|signed\s+|struct\s+|enum\s+)*"
    r"[A-Za-z_][A-Za-z0-9_]*(?:\s*[&*]+\s*|\s+)[A-Za-z_][A-Za-z0-9_]*\s*\(",
    re.MULTILINE,
)


def _match_delim(text: str, start: int, open_ch: str, close_ch: str, masked: set[int]) -> int | None:
    """Index just past the delimiter matching the one at ``start`` (-1 if unbalanced)."""
    depth = 0
    for i in range(start, len(text)):
        if i in masked:
            continue
        ch = text[i]
        if ch == open_ch:
            depth += 1
        elif ch == close_ch:
            depth -= 1
            if depth == 0:
                return i + 1
    return None


@register
class CCppAnalyzer(Analyzer):
    name = "ccpp"
    extensions = (".c", ".cpp", ".cc", ".cxx", ".h", ".hpp", ".hh")
    strong_sinks = STRONG_SINKS
    sinks = ALL_SINKS
    system_prompt = Analyzer.build_system_prompt(
        "Analyze the provided C/C++ function for memory-safety and injection "
        "vulnerabilities: buffer overflows, off-by-one, format strings, command "
        "injection, use-after-free, double free, integer overflow leading to small "
        "allocations, unchecked return values on size-bearing calls, TOCTOU on "
        "filesystem paths."
    )

    def chunk(self, content: str, path: str = "") -> list[Chunk]:
        masked = mask_positions(content)
        chunks: list[Chunk] = []
        for m in _SIG_RE.finditer(content):
            # Skip hits inside comments/strings and control statements.
            if m.start() in masked:
                continue
            line_start = content.rfind("\n", 0, m.start()) + 1
            head = content[line_start : m.start()].strip()
            if head and not re.fullmatch(r"[\w\s\*&:,<>#\[\]]+", head):
                continue
            if re.search(r"\b(if|for|while|switch|return|sizeof|case)\s*$", head):
                continue
            open_paren = content.find("(", m.start())
            if open_paren == -1 or open_paren in masked:
                continue
            close_paren = _match_delim(content, open_paren, "(", ")", masked)
            if close_paren is None:
                continue
            # Only a definition when the next code char after ')' is '{'.
            rest = re.match(r"\s*", content[close_paren:])
            brace_pos = close_paren + rest.end()
            if not content.startswith("{", brace_pos) or brace_pos in masked:
                continue
            end = _match_delim(content, brace_pos, "{", "}", masked)
            if end is None:
                continue
            fn_name = re.search(r"([A-Za-z_][A-Za-z0-9_]*)\s*\($", content[m.start() : open_paren + 1])
            chunks.append(
                Chunk(
                    name=fn_name.group(1) if fn_name else "<anonymous>",
                    line=content.count("\n", 0, m.start()) + 1,
                    code=content[m.start() : end].strip(),
                )
            )
        return chunks or [Chunk(name="file_scope", line=1, code=content.strip())]
