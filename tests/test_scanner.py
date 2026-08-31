from vharness.scanner import discover_files, scan


def test_dry_run_reports_plan_without_client(tmp_path):
    (tmp_path / "app.c").write_text(
        "void vulnerable(char *in) {\n  char buf[8];\n  strcpy(buf, in);\n}\n", encoding="utf-8"
    )
    (tmp_path / "clean.c").write_text("int add(int a, int b) {\n  return a + b;\n}\n", encoding="utf-8")
    (tmp_path / "install.sh").write_text(
        "#!/usr/bin/env bash\ncurl -fsSL https://example.com/i.sh | sh\n", encoding="utf-8"
    )
    (tmp_path / "notes.txt").write_text("strcpy is dangerous\n", encoding="utf-8")

    result = scan([str(tmp_path)], None, dry_run=True)
    assert result.stats.files_seen == 4
    assert result.stats.files_no_analyzer == 1  # .txt
    assert result.stats.files_gated_out == 1    # clean.c has no strong sink
    assert result.stats.files_analyzed == 2
    plan = result.dry_run_plan
    assert (plan and len(plan)) == 2
    targets = {(f, c) for f, c, _l in plan}
    assert ("app.c", "vulnerable") in targets
    assert ("install.sh", "<script>") in targets


def test_discover_skips_excluded_dirs(tmp_path):
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "evil.js").write_text("eval(1)", encoding="utf-8")
    (tmp_path / "src.js").write_text("eval(1)", encoding="utf-8")
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "x.sh").write_text("#!/bin/sh\n", encoding="utf-8")

    found = discover_files([str(tmp_path)])
    names = [f.split("/")[-1] for f in found]
    assert names == ["src.js"]
