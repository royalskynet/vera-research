"""交付报告不得带出凭证或本机路径：泄漏一旦写进正文，发布即外流。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import validate_report as vr  # noqa: E402


def test_credentials_and_home_path_are_caught():
    text = (
        "正文 /Users/someone/notes.md\n"
        "token ghp_abcdefghijklmnopqrstuvwxyz123456\n"
        "key sk-abcdefghijklmnopqrstuvwxyz\n"
        "-----BEGIN RSA PRIVATE KEY-----\n"
    )
    found = vr.check_leaks(text)
    labels = " ".join(found)
    assert "local home path" in labels
    assert "GitHub token" in labels
    assert "OpenAI-style key" in labels
    assert "PEM private key" in labels


def test_clean_report_body_has_no_leaks():
    text = "帮助中心说明可用支付方式取决于 KYC 地区 [1]。\n参考 https://example.com/help/agent\n"
    assert vr.check_leaks(text) == []
