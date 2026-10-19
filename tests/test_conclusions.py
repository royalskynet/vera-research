"""主要结论必须先正面回答问题：只贴条文、不给答案的结论条目要被挡下。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import validate_report as vr  # noqa: E402


def test_fact_dump_conclusion_is_rejected():
    text = "主要结论：\n\n- 帮助中心明示可用支付方式取决于 KYC 地区 [1]。\n\n## 二、覆盖范围与方法\n"
    errors, _ = vr.check_conclusions(text)
    assert any("bold direct answer" in e for e in errors)


def test_bold_answer_first_passes_and_nested_bullets_ignored():
    text = ("> **一句话结论**：可以。\n\n### 1.3 主要结论\n\n"
            "1. **可以，但限额较低。** 依据 [1]。\n  - 补充说明 [2]\n"
            "2. **不可以。** 依据 [3]。\n\n---\n")
    errors, warnings = vr.check_conclusions(text)
    assert errors == [] and warnings == []


def test_missing_one_line_answer_warns():
    _, warnings = vr.check_conclusions("主要结论：\n\n- **可以。** [1]\n")
    assert warnings == ["missing 一句话结论 line"]


def test_dimension_sections_must_follow_d_numbers():
    # 曾按「維度權重」把 D2 排在 D1 前，讀者對不上編號；章節與矩陣都要照 D1..D9
    text = "### D2 牌照\n\n### D1 主体\n\n| D3 合规 | 中 |\n| D1 主体 | 低 |\n"
    errors = vr.check_dim_order(text)
    assert len(errors) == 2
    assert vr.check_dim_order("### D1 主体\n\n### D2 牌照\n\n| D1 | 低 |\n| D2 | 中 |\n") == []
