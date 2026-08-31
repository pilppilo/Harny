"""Distro config analyzer: sudoers.d, systemd units, udev rules, pacman hooks, sysctl.

These files are small and always security-relevant, so there is no sink gate
(strong_sinks=None) and chunking is whole-file.
"""

from __future__ import annotations

import re

from .base import Analyzer, Chunk, register

_SYSTEMD_EXTS = (".service", ".socket", ".timer", ".path", ".mount", ".target")


def _looks_like_sudoers(path: str, first_bytes: bytes) -> bool:
    if "sudoers" in path.lower():
        return True
    head = first_bytes[:2000].decode("utf-8", "replace")
    return bool(re.search(r"^\s*(?:%?\S+\s+)?ALL\s*=|^%wheel\b|NOPASSWD", head, re.MULTILINE)) and "=" in head and "[Unit]" not in head


@register
class DistroConfAnalyzer(Analyzer):
    name = "distroconf"
    strong_sinks = None  # always analyze matched files
    max_chunk_chars = 20_000
    system_prompt = Analyzer.build_system_prompt(
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
        lower = path.lower()
        if lower.endswith(_SYSTEMD_EXTS) and "[Unit]" in first_bytes[:4000].decode("utf-8", "replace"):
            return True
        if lower.endswith(".rules") and ("==" in first_bytes.decode("utf-8", "replace") or "=" in first_bytes.decode("utf-8", "replace")):
            head = first_bytes[:2000].decode("utf-8", "replace")
            if re.search(r"^(?:ACTION|KERNEL|SUBSYSTEM|ATTR|ENV)\s*[=!]=+", head, re.MULTILINE):
                return True
        if lower.endswith(".hook") and "[Trigger]" in first_bytes[:4000].decode("utf-8", "replace"):
            return True
        if "sysctl.d" in lower or ("sysctl" in lower and lower.endswith(".conf")):
            return True
        if _looks_like_sudoers(lower, first_bytes):
            return True
        return False

    def chunk(self, content: str, path: str = "") -> list[Chunk]:
        return [Chunk(name="<config>", line=1, code=content.strip())]
