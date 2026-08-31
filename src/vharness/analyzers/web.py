"""Web-language analyzer: JS/TS/PHP/Python (+ QML for desktop-shell UIs)."""

from __future__ import annotations

import re

from ..textutil import mask_positions
from .base import Analyzer, Chunk, register

# File gate — only files with genuinely risky constructs proceed to the model.
STRONG_SINKS = re.compile(
    r"eval\s*\(|new\s+Function\s*\(|require\s*\(\s*['\"]child_process|child_process|"
    r"\.execSync\s*\(|execSync\s*\(|\bexec\s*\(|\bexecFile\b|spawnSync|shell_exec|"
    r"passsthru|proc_open|popen\s*\(|os\.system|os\.popen|subprocess|shell\s*=\s*True|"
    r"pickle\.loads?\s*\(|yaml\.load\s*\(|marshal\.loads|unserialize\s*\(|"
    r"\.innerHTML|document\.write|dangerouslySetInnerHTML|v-html|insertAdjacentHTML|"
    r"\.execute\s*\(|cursor\.execute|query\s*\(\s*[`'\"]\s*(?:SELECT|INSERT|UPDATE|DELETE|ALTER)|"
    r"\$_(?:GET|POST|REQUEST|COOKIE)|vm\.runIn|render_template_string|"
    r"include\s*\$|require\s*\$|readFile\s*\(|file_get_contents\s*\(\s*\$"
)

# Chunk gate — strong sinks plus taint-entry points worth auditing in context.
ALL_SINKS = re.compile(
    r"eval\s*\(|new\s+Function|child_process|\bexec\b|execSync|spawnSync|shell_exec|"
    r"os\.system|os\.popen|subprocess|shell\s*=\s*True|pickle\.loads|yaml\.load|"
    r"unserialize\s*\(|\.innerHTML|document\.write|dangerouslySetInnerHTML|"
    r"\.execute\s*\(|cursor\.execute|\$_(?:GET|POST|REQUEST|COOKIE)|vm\.runIn|"
    r"render_template_string|include\s*\$|require\s*\$|"
    r"req\.(?:query|params|body|cookies)|request\.(?:GET|POST|ARGS|FORM)|params\[|"
    r"localStorage|\.send\s*\(|\.render\s*\(|res\.redirect|url_for|open\s*\(|"
    r"\.one\(|\.all\(|requests\.(?:get|post)|fetch\s*\("
)

_BRACE_HEADS = re.compile(
    r"(?:function\s+(?:async\s+)?(?P<fn>[A-Za-z_$][\w$]*)\s*\()"
    r"|(?:const|let|var)\s+(?P<arrow>[A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?\([^)]*\)\s*(?:=>|{)"
    r"|(?:(?P<method>[A-Za-z_$][\w$]*)\s*:\s*(?:async\s*)?function\s*\()"
)
_KEYWORDS = {"if", "for", "while", "switch", "catch", "return", "function", "typeof", "delete", "in", "of", "new", "do", "else", "try", "with"}
_PY_DEF = re.compile(r"^(\s*)(?:async\s+)?def\s+([A-Za-z_]\w*)\s*\(", re.MULTILINE)


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
class WebAnalyzer(Analyzer):
    name = "web"
    extensions = (".js", ".ts", ".jsx", ".tsx", ".mjs", ".cjs", ".php", ".py", ".qml")
    strong_sinks = STRONG_SINKS
    sinks = ALL_SINKS
    system_prompt = Analyzer.build_system_prompt(
        "Analyze the provided web application code (JavaScript/TypeScript, PHP, "
        "Python, or QML) for: cross-site scripting, SQL injection, command "
        "injection, path traversal, SSRF, insecure deserialization, server-side "
        "template injection, unsafe redirect, and secrets in code. Focus on "
        "user-controlled input reaching a dangerous sink."
    )

    def chunk(self, content: str, path: str = "") -> list[Chunk]:
        if path.lower().endswith(".py") or self._looks_python(content):
            return self._chunk_python(content)
        masked = mask_positions(content)
        chunks: list[Chunk] = []
        for m in _BRACE_HEADS.finditer(content):
            if m.start() in masked:
                continue
            name = m.group("fn") or m.group("arrow") or m.group("method") or "<anon>"
            if name in _KEYWORDS:
                continue
            brace = content.find("{", m.start())
            while brace != -1 and brace in masked:
                brace = content.find("{", brace + 1)
            if brace == -1:
                continue
            end = _brace_end(content, brace, masked)
            if end is None:
                continue
            start = m.start()
            chunks.append(
                Chunk(
                    name=name,
                    line=content.count("\n", 0, start) + 1,
                    code=content[start:end].strip(),
                )
            )
        if not chunks and len(content) <= self.max_chunk_chars:
            return [Chunk(name="file_scope", line=1, code=content.strip())]
        return chunks

    def _looks_python(self, content: str) -> bool:
        head = content[:2000]
        has_js = bool(re.search(r"\bfunction\s*\w*\s*\(|=>|<\?php|\$\w+\s*=|import\s+Qt", head))
        if has_js:
            return False
        return bool(
            re.search(r"^\s*(?:import\s+[\w.]+|from\s+[\w.]+\s+import|def\s+\w+\s*\(|class\s+\w+\s*[:(])", head, re.MULTILINE)
        )

    def _chunk_python(self, content: str) -> list[Chunk]:
        chunks: list[Chunk] = []
        matches = list(_PY_DEF.finditer(content))
        for i, m in enumerate(matches):
            indent = len(m.group(1))
            start = m.start()
            end = len(content)
            for candidate in matches[i + 1 :]:
                if len(candidate.group(1)) <= indent:
                    end = candidate.start()
                    break
            # Extend end to include same-indent trailing lines (decorators above
            # are ignored; body runs until the next def/class at <= indent).
            chunks.append(
                Chunk(
                    name=m.group(2),
                    line=content.count("\n", 0, start) + 1,
                    code=content[start:end].strip(),
                )
            )
        return chunks or [Chunk(name="file_scope", line=1, code=content.strip())]
