"""禁詞掃描的 URL 例外：被引來源 URL 原文含禁詞不算違規，正文含才算。"""
import subprocess
from pathlib import Path

CHECK = Path(__file__).resolve().parents[1] / "scripts" / "check_report.sh"
HEAD = "# 测试报告\n\n这是一段说明文字 [1]\n"
REFS = "\n## 参考资料\n\n[1] 存档页面 https://web.archive.org/web/2024/https://example.com/a\n"


def run(report: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(CHECK), str(report)],
        capture_output=True, text=True,
    )


def test_forbidden_word_only_inside_url_passes(tmp_path):
    report = tmp_path / "r.md"
    report.write_text(HEAD + REFS, encoding="utf-8")
    out = run(report)
    assert out.returncode == 0, out.stdout + out.stderr
    assert "FORBIDDEN CAUGHT" not in out.stdout


def test_forbidden_word_in_body_still_fails(tmp_path):
    report = tmp_path / "r.md"
    report.write_text(HEAD + "\n这份报告的爬取方式另述 [1]\n" + REFS, encoding="utf-8")
    out = run(report)
    assert out.returncode != 0
    assert "pattern [爬取]" in out.stdout
