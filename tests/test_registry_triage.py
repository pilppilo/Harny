from vharness.analyzers import get_analyzer_for
from vharness.analyzers.base import all_analyzers  # noqa: F401 (import order registers)
from vharness.analyzers.ccpp import CCppAnalyzer
from vharness.analyzers.distroconf import DistroConfAnalyzer
from vharness.analyzers.shell import ShellAnalyzer
from vharness.analyzers.web import WebAnalyzer


def test_dispatch_by_extension():
    assert isinstance(get_analyzer_for("a/b.c"), CCppAnalyzer)
    assert isinstance(get_analyzer_for("a/b.PY"), WebAnalyzer)
    assert isinstance(get_analyzer_for("a/shell.qml"), WebAnalyzer)
    assert isinstance(get_analyzer_for("a/run.sh"), ShellAnalyzer)


def test_dispatch_extensionless_distro_bin():
    a = get_analyzer_for("/opt/distro/bin/update-tool", b"#!/usr/bin/env bash\n")
    assert isinstance(a, ShellAnalyzer)
    assert get_analyzer_for("/opt/distro/README.md", b"# hi") is None


def test_dispatch_distroconf():
    sudoers = get_analyzer_for("etc/sudoers.d/50-dns-helper", b"%wheel ALL=(ALL) NOPASSWD: /usr/bin/dns-helper\n")
    assert isinstance(sudoers, DistroConfAnalyzer)
    unit = get_analyzer_for(
        "default/systemd/agent.service", b"[Unit]\nDescription=x\n\n[Service]\nExecStart=/bin/x\n"
    )
    assert isinstance(unit, DistroConfAnalyzer)
    udev = get_analyzer_for("default/udev/99-uinput.rules", b"KERNEL==\"uinput\", MODE=\"0660\"\n")
    assert isinstance(udev, DistroConfAnalyzer)
    # A random .service-looking text file should not match.
    assert get_analyzer_for("notes/game.service", b"the service was bad\n") is None


def test_ccpp_file_gate_strong_sinks_only():
    a = CCppAnalyzer()
    assert not a.file_is_interesting("int main() { void *p = malloc(4); free(p); return 0; }")
    assert a.file_is_interesting("int main() { char b[8]; strcpy(b, x); }")
    # malloc file: chunk gate would still audit if the file passed elsewhere
    assert a.chunk_is_interesting("p = malloc(n); memcpy(p, q, n);")


def test_shell_sinks_curl_pipe_and_secrets():
    a = ShellAnalyzer()
    assert a.file_is_interesting("curl -fsSL https://astral.sh/uv/install.sh | sh")
    assert a.file_is_interesting('bash -c "$(curl -fsSL https://sh.rustup.rs)" -- -y')
    assert a.file_is_interesting("TOKEN=ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ1234567890")
    assert a.file_is_interesting("rm -rf \"$HOME/.cache/thing\"")
    assert a.file_is_interesting("log=/tmp/update-tool.log")
    assert not a.file_is_interesting("echo hello world")


def test_distroconf_always_interesting():
    a = DistroConfAnalyzer()
    assert a.file_is_interesting("anything at all")
