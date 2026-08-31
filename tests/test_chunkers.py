from vharness.analyzers.ccpp import CCppAnalyzer
from vharness.analyzers.shell import ShellAnalyzer
from vharness.analyzers.web import WebAnalyzer


C_SRC = """
#include <string.h>

int helper(int a, int b);  /* prototype, must be skipped */

void vulnerable(char *in) {
    char buf[32];
    if (in) { strcpy(buf, in); }  /* brace in comment: } */
    printf("%s\\n", buf);
}

void safe(void) {
    helper(1, 2);
}
"""


def test_ccpp_chunks_functions_not_prototypes():
    chunks = CCppAnalyzer().chunk(C_SRC)
    names = [c.name for c in chunks]
    assert "helper" not in names
    assert names == ["vulnerable", "safe"]
    vuln = chunks[0]
    assert vuln.line == 6
    assert vuln.code.startswith("void vulnerable")
    assert vuln.code.rstrip().endswith("}")


def test_ccpp_handles_fn_pointer_signature():
    src = "void run(int (*cb)(void *, size_t), void *ctx) { cb(ctx, 4); }"
    chunks = CCppAnalyzer().chunk(src)
    assert [c.name for c in chunks] == ["run"]


def test_ccpp_fallback_file_scope():
    chunks = CCppAnalyzer().chunk("int x = 1; // no functions\n")
    assert len(chunks) == 1
    assert chunks[0].name == "file_scope"


SHELL_SRC = (
    "#!/usr/bin/env bash\nset -euo pipefail\n\n"
    "prepare() {\n  mkdir -p /tmp/work\n}\n\n"
    "curl -fsSL https://example.com/install.sh | sh\n"
    "install_deps() {\n  pacman -Syu --noconfirm base-devel\n}\n\n"
    + "# pad so the file exceeds the whole-file threshold\n" + "echo filler line\n" * 280
)


def test_shell_chunks_functions_and_toplevel():
    chunks = ShellAnalyzer().chunk(SHELL_SRC)
    names = [c.name for c in chunks]
    assert "prepare" in names and "install_deps" in names
    top = [c for c in chunks if c.name == "<top-level>"]
    assert any("curl -fsSL" in c.code for c in top)
    lines = [c.line for c in chunks]
    assert lines == sorted(lines)


def test_shell_small_file_is_whole():
    src = "#!/bin/sh\ncurl http://x | sh\n"
    chunks = ShellAnalyzer().chunk(src)
    assert len(chunks) == 1
    assert chunks[0].name == "<script>"


def test_shell_matches_extensionless_by_shebang():
    a = ShellAnalyzer()
    assert a.matches("/opt/distro/bin/update-tool", b"#!/usr/bin/env bash\n# script")
    assert a.matches("/opt/distro/bin/tool", b"#!/bin/sh\nexec thing")
    assert not a.matches("/opt/distro/bin/tool.py", b"#!/usr/bin/env python3\n")
    assert not a.matches("/opt/distro/bin/tool", b"#!/usr/bin/env python3\nprint(1)\n")


PY_SRC = """import os

def handler(name):
    cmd = f"echo {name}"
    os.system(cmd)

class Thing:
    def inner(self):
        return 1

def top():
    return 2
"""


def test_web_python_def_chunking():
    chunks = WebAnalyzer().chunk(PY_SRC)
    names = [c.name for c in chunks]
    assert names == ["handler", "inner", "top"]
    assert "os.system" in chunks[0].code


def test_web_js_function_chunking():
    src = "function handle(req) {\n  const out = eval(req.body);\n  return out;\n}\nconst safe = 1;\n"
    chunks = WebAnalyzer().chunk(src)
    assert any(c.name == "handle" and "eval" in c.code for c in chunks)
