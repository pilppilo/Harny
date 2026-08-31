"""Shell (bash/sh) analyzer for distro/tool repos and installer scripts.

Matches extensionless scripts by shebang (many distros ship CLI scripts
without a .sh suffix). Chunks bash functions AND top-level segments, since
install scripts are mostly top-level code.
"""

from __future__ import annotations

import re

from .base import Analyzer, Chunk, register

# File gate — scripts worth an LLM look at all.
STRONG_SINKS = re.compile(
    # curl/wget piped into a shell, or command-substituted into one
    r"(?:curl|wget)[^|\n]*\|\s*(?:sudo\s+)?(?:ba|z|da)?sh\b"
    r'|\b(?:ba|z)?sh\s+-c\s*"\$\((?:curl|wget)'
    r"|\beval\s+(?:\"|')?\$"
    r"|base64\s+(?:-d|--decode)[^|\n]*\|\s*(?:ba|z)?sh"
    r"|source\s*<\(\s*(?:curl|wget)"
    r"|\bsudo\b.*\b(?:rm|tee|chmod|chown|dd|mkfs|pvcreate|sysctl|tee)\b"
    r"|\brm\s+(?:-[a-z]*r[a-z]*f|-[a-z]*f[a-z]*r)\b"
    r"|rm\s+(?:-[a-z]*r[a-z]*f|-[a-z]*f[a-z]*r)\s+[\"']?/|rm\s+(?:-[a-z]*r[a-z]*f|-[a-z]*f[a-z]*r)\s+\$"
    r"|chmod\s+(?:a\+|ugo\+|777|666)\b"
    r"|/tmp/[A-Za-z0-9_.-]+"
    r"|(?:curl|wget)[^#\n]*(?:\|\s*tar|chmod\s+\+x|--exec)"
    r"|(?:BEGIN\s+(?:RSA|EC|OPENSSH|DSA|PGP)\s+PRIVATE\s+KEY|"
    r"AKIA[0-9A-Z]{16}|gh[pousr]_[A-Za-z0-9]{20,}|xox[baprs]-[A-Za-z0-9-]{10,}|"
    r"sk-[A-Za-z0-9]{20,}|-----BEGIN\s+.*TOKEN-----)"
    r"|\bnc\s+-[le]|/dev/tcp"
    r"|StrictHostKeyChecking\s*=\s*(?:no|accept-new)"
    r"|curl[^#\n]*-k\b|wget[^#\n]*--no-check-certificate"
)

# Chunk gate — everything above plus weaker signals that matter in context.
ALL_SINKS = re.compile(
    r"eval\s+|curl|wget|\bsudo\b|\brm\s+-rf|\btee\b|chmod|chown|/tmp/|/dev/tcp|"
    r"base64|printf\s+.*\\x|read\s+-r|tr\s+-d|xargs|find\s+.*-exec|command\s+-v|"
    r"\$\(\s*\(|\$\{[A-Za-z_][A-Za-z0-9_]*(?::|%|/|\^|,)[^}]*\}|secret|token|password|api[_-]?key"
)

_SHEBANG = re.compile(rb"^#!.*\b(?:ba|z|)sh\b")
_FUNC_HEAD = re.compile(r"^\s*(?:function\s+)?([A-Za-z_][\w-]*)\s*\(\)\s*\{", re.MULTILINE)


def _line_of(content: str, pos: int) -> int:
    return content.count("\n", 0, pos) + 1


def _mask_shell(text: str) -> set[int]:
    """Positions inside single/double-quoted strings and heredocs (best effort)."""
    masked: set[int] = set()
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if ch == "#":
            j = text.find("\n", i)
            j = n if j == -1 else j
            masked.update(range(i, j))
            i = j
        elif ch in "'\"":
            j = i + 1
            while j < n:
                if text[j] == "\\" and ch == '"':
                    j += 2
                    continue
                if text[j] == ch:
                    break
                j += 1
            masked.update(range(i, min(j + 1, n)))
            i = j + 1
        else:
            i += 1
    return masked


def _brace_end(text: str, open_idx: int, masked: set[int]) -> int | None:
    depth = 0
    for i in range(open_idx, len(text)):
        if i in masked:
            continue
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return i + 1
    return None


@register
class ShellAnalyzer(Analyzer):
    name = "shell"
    extensions = (".sh", ".bash", ".zsh")
    strong_sinks = STRONG_SINKS
    sinks = ALL_SINKS
    max_chunk_chars = 10_000
    system_prompt = Analyzer.build_system_prompt(
        "Analyze the provided shell script (bash) as it would run on a Linux "
        "distro. Look for: curl|bash-style execution of unverified remote code, "
        "downloads executed or chmod +x'd without checksum/signature "
        "verification, command injection through unquoted variable expansion, "
        "argument injection into sudo-privileged helpers, rm -rf on "
        "variable-controlled paths, predictable fixed paths in /tmp (symlink "
        "races), writes to system files via tee/heredoc, credential or token "
        "exposure, weakened TLS or host-key checks, and unsafe device node "
        "permission changes. Only report issues a real attacker could abuse; "
        "do not report style or quoting nits."
    )

    def matches(self, path: str, first_bytes: bytes) -> bool:
        if path.lower().endswith(self.extensions):
            return True
        # Extensionless executable scripts (distro bin/ dirs) — route by shebang.
        return bool(_SHEBANG.match(first_bytes))

    def chunk(self, content: str, path: str = "") -> list[Chunk]:
        masked = _mask_shell(content)
        if len(content) <= 4000:
            return [Chunk(name="<script>", line=1, code=content.strip())]

        chunks: list[Chunk] = []
        spans: list[tuple[int, int, str]] = []  # (start, end, name)
        for m in _FUNC_HEAD.finditer(content):
            if m.start() in masked:
                continue
            brace = content.find("{", m.start())
            if brace == -1:
                continue
            end = _brace_end(content, brace, masked)
            if end is None:
                continue
            spans.append((m.start(), end, m.group(1)))

        # Top-level segments = gaps between functions, split to size.
        prev = 0
        for start, end, _name in spans:
            self._push_segment(chunks, content, prev, start)
            prev = end
        self._push_segment(chunks, content, prev, len(content))

        for start, end, name in spans:
            chunks.append(
                Chunk(name=name, line=_line_of(content, start), code=content[start:end].strip())
            )
        chunks.sort(key=lambda c: c.line)
        return chunks or [Chunk(name="<script>", line=1, code=content.strip())]

    def _push_segment(self, chunks: list[Chunk], content: str, a: int, b: int) -> None:
        seg = content[a:b]
        text = seg.strip()
        if not text or len(text) < 40:
            return
        lead = len(seg) - len(seg.lstrip())
        base_line = content.count("\n", 0, a) + 1 + seg[:lead].count("\n")
        max_len = self.max_chunk_chars
        lines = text.splitlines(keepends=True)
        buf: list[str] = []
        size = 0
        buf_line = base_line
        cur_line = base_line
        for line in lines:
            if size + len(line) > max_len and buf:
                chunks.append(Chunk(name="<top-level>", line=buf_line, code="".join(buf).strip()))
                buf, size, buf_line = [], 0, cur_line
            buf.append(line)
            size += len(line)
            cur_line += 1
        if buf and "".join(buf).strip():
            chunks.append(Chunk(name="<top-level>", line=buf_line, code="".join(buf).strip()))
