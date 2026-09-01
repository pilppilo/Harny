"""Probe discovery/triage/dry-run behavior (ported from legacy scanner tests)."""

from vharness.probes import domains


def test_shell_probe_routes_and_triages(tmp_path):
    (tmp_path / "app.c").write_text(
        "void vulnerable(char *in) {\n  char buf[8];\n  strcpy(buf, in);\n}\n", encoding="utf-8"
    )
    (tmp_path / "clean.c").write_text("int add(int a, int b) {\n  return a + b;\n}\n", encoding="utf-8"
    )
    (tmp_path / "install.sh").write_text(
        "#!/usr/bin/env bash\ncurl -fsSL https://example.com/i.sh | sh\n", encoding="utf-8"
    )
    (tmp_path / "notes.txt").write_text("strcpy is dangerous\n", encoding="utf-8")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "evil.js").write_text("eval(userInput)", encoding="utf-8")

    ccpp = domains.CCppProbe()
    shell = domains.ShellProbe()

    ccpp_attempts = ccpp.attempts(targets=[str(tmp_path)])
    shell_attempts = shell.attempts(targets=[str(tmp_path)])

    # clean.c has no strong sink → triaged out; app.c yields one attempt.
    assert len(ccpp_attempts) == 1
    assert ccpp_attempts[0].context["function"] == "vulnerable"
    assert ccpp_attempts[0].source.endswith("app.c")
    # install.sh matches by extension; the .txt and node_modules are ignored.
    assert len(shell_attempts) == 1
    assert shell_attempts[0].source.endswith("install.sh")
    assert shell_attempts[0].probe == "shell"


def test_probe_excludes_dirs(tmp_path):
    (tmp_path / "vendor").mkdir()
    (tmp_path / "vendor" / "x.sh").write_text("curl http://x | sh\n", encoding="utf-8")
    (tmp_path / "root.sh").write_text("curl http://y | sh\n", encoding="utf-8")
    got = domains.ShellProbe().attempts(targets=[str(tmp_path)])
    assert [a.source for a in got] == ["root.sh"]


def test_extensionless_routed_by_shebang(tmp_path):
    p = tmp_path / "tool"  # no extension
    p.write_text("#!/usr/bin/env bash\nset -euo pipefail\ncurl -fsSL https://x/i.sh | sh\n", encoding="utf-8")
    got = domains.ShellProbe().attempts(targets=[str(p)])
    assert len(got) == 1 and got[0].source == str(p)
