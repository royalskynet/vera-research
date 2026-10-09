"""第三輪反方稽核必跑：第二模型（codex → opencode）優先，都不行才退 subagent；報告含私人 PII 不得送外部模型。"""
import os
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "devils_advocate.sh"
GOOD_PACK = "# Devil's Advocate Evidence Pack\\n\\n## 爭點 1\\nOBJECTION: NO_EVIDENCE_BACKED_OBJECTION\\n"


def _fake(bin_dir, name, writes_pack):
    body = f'printf "{GOOD_PACK}" > "$DA_OUT"' if writes_pack else "exit 1"
    p = bin_dir / name
    p.write_text(f'#!/bin/sh\ntouch "{bin_dir}/{name}.called"\n{body}\n')
    p.chmod(0o755)


def _run(tmp_path, report_text, codex_ok, opencode_ok):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    if codex_ok is not None:
        _fake(bin_dir, "codex", codex_ok)
    if opencode_ok is not None:
        _fake(bin_dir, "opencode", opencode_ok)
    report = tmp_path / "report.md"
    report.write_text(report_text)
    out = tmp_path / "audit" / "da.md"
    env = {**os.environ, "PATH": f"{bin_dir}:/usr/bin:/bin"}
    r = subprocess.run(["bash", str(SCRIPT), str(report), str(out)], capture_output=True, text=True, env=env)
    return r, bin_dir, out


def test_codex_first(tmp_path):
    r, bin_dir, out = _run(tmp_path, "# 报告\n结论 [1]\n", True, True)
    assert r.returncode == 0 and "ENGINE=codex" in r.stdout
    assert not (bin_dir / "opencode.called").exists()
    assert "Engine: codex" in out.read_text()


def test_falls_to_opencode_when_codex_pack_invalid(tmp_path):
    r, _, _ = _run(tmp_path, "# 报告\n", False, True)
    assert r.returncode == 0 and "ENGINE=opencode" in r.stdout


def test_no_second_model_means_subagent(tmp_path):
    r, _, _ = _run(tmp_path, "# 报告\n", None, None)
    assert r.returncode == 3 and "reason=no_second_model" in r.stdout


def test_pii_never_reaches_external_model(tmp_path):
    r, bin_dir, _ = _run(tmp_path, "# 报告\n联系 someone@example.com\n", True, True)
    assert r.returncode == 3 and "reason=pii_in_report" in r.stdout
    assert not (bin_dir / "codex.called").exists()
