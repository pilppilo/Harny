"""Built-in domain probes: ccpp, web, shell, distroconf.

Thin adapters over the per-language chunkers in vharness.analyzers — the
chunking/triage logic stays in one place; probes add the Attempt plumbing
and routing for multi-probe scans.
"""

from __future__ import annotations

import re

from ..analyzers import ccpp as _ccpp
from ..analyzers import distroconf as _distroconf
from ..analyzers import shell as _shell
from ..analyzers import web as _web
from ..core import PROBE_REGISTRY
from .base import register_builtin
from .scan import FileProbe, ROUTING_HEADER_BYTES


@register_builtin
class CCppProbe(FileProbe):
    name = "ccpp"
    help = "C/C++ memory-safety & injection review"
    extensions = _ccpp.CCppAnalyzer.extensions
    strong_sinks = _ccpp.STRONG_SINKS
    sinks = _ccpp.ALL_SINKS
    role = (
        "Analyze the provided C/C++ function for memory-safety and injection "
        "vulnerabilities: buffer overflows, off-by-one, format strings, command "
        "injection, use-after-free, double free, integer overflow leading to small "
        "allocations, unchecked return values on size-bearing calls, TOCTOU on "
        "filesystem paths."
    )

    def chunk(self, content: str, path: str = "") -> list[tuple[str, int, str]]:
        return [(c.name, c.line, c.code) for c in _ccpp.CCppAnalyzer().chunk(content, path)]


@register_builtin
class WebProbe(FileProbe):
    name = "web"
    help = "JS/TS/PHP/Python/QML web-vuln review"
    extensions = _web.WebAnalyzer.extensions
    strong_sinks = _web.STRONG_SINKS
    sinks = _web.ALL_SINKS
    role = (
        "Analyze the provided web application code (JavaScript/TypeScript, PHP, "
        "Python, or QML) for: cross-site scripting, SQL injection, command "
        "injection, path traversal, SSRF, insecure deserialization, server-side "
        "template injection, unsafe redirect, and secrets in code. Focus on "
        "user-controlled input reaching a dangerous sink."
    )

    def chunk(self, content: str, path: str = "") -> list[tuple[str, int, str]]:
        return [(c.name, c.line, c.code) for c in _web.WebAnalyzer().chunk(content, path)]


@register_builtin
class ShellProbe(FileProbe):
    name = "shell"
    help = "bash/sh distro & installer script review"
    extensions = _shell.ShellAnalyzer.extensions
    strong_sinks = _shell.STRONG_SINKS
    sinks = _shell.ALL_SINKS
    max_chunk_chars = _shell.ShellAnalyzer.max_chunk_chars
    role = (
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
        a = _shell.ShellAnalyzer()
        return a.matches(path, first_bytes)

    def chunk(self, content: str, path: str = "") -> list[tuple[str, int, str]]:
        return [(c.name, c.line, c.code) for c in _shell.ShellAnalyzer().chunk(content, path)]


@register_builtin
class DistroConfProbe(FileProbe):
    name = "distroconf"
    help = "sudoers/systemd/udev/sysctl/pacman-hook hardening review"
    strong_sinks = None
    max_chunk_chars = 20_000
    role = (
        "Analyze the provided Linux distribution configuration file (sudoers "
        "drop-in, systemd unit, udev rule, pacman/alpm hook, or sysctl "
        "drop-in) from an OS-hardening perspective. Look for: overly broad "
        "NOPASSWD sudo grants (especially with wildcards or regex arguments "
        "that a user could abuse to run arbitrary commands), missing systemd "
        "sandboxing on units running with privileges (ProtectSystem, "
        "PrivateTmp, NoNewPrivileges, DynamicUser, RestrictAddressFamilies), "
        "udev rules setting world- or group-writable device modes, sysctl "
        "values weakening kernel protections (e.g. accept_source_route, "
        "unprotected bpf/ptrace, kptr_restrict=0), pacman hooks executing "
        "scripts from writable paths, and anything that widens privilege or "
        "weakens isolation. Report only genuine hardening gaps, not stylistic "
        "preferences."
    )

    def matches(self, path: str, first_bytes: bytes) -> bool:
        return _distroconf.DistroConfAnalyzer().matches(path, first_bytes)

    def chunk(self, content: str, path: str = "") -> list[tuple[str, int, str]]:
        return [("<config>", 1, content.strip())] if content.strip() else []


def route_file(path: str) -> str | None:
    """Pick the first built-in probe whose matches() accepts this file."""
    for name in PROBE_REGISTRY.names():
        probe = PROBE_REGISTRY.instantiate(name)
        if not isinstance(probe, FileProbe):
            continue
        try:
            with open(path, "rb") as fh:
                head = fh.read(ROUTING_HEADER_BYTES)
        except OSError:
            return None
        if probe.matches(path, head):
            return name
    return None
