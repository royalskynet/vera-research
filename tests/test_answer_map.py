"""Answer coverage gate: ledger question -> answer map -> report sentence."""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import validate_report as vr  # noqa: E402

REPORT = """# 某厂商尽调报告

> **一句话结论**：该厂商或可附条件推进，香港牌照已在名册核实 [1]。

## 主要结论

- **持牌**：香港 TCSP 名册列有该主体 [1]。
- **未能核实**：本次已查阅的公开来源未能确认其托管方身份。

## 参考资料

[1] 香港公司注册处 TCSP 名册 https://example.com/tcsp
"""


def _ledger(core="该厂商能否作为 KYT 供应商", require=True):
    led = {
        "cells": {
            "V/D2": {"questions": [
                {"id": "Q1", "q": "是否持有香港 TCSP 牌照", "state": "answered", "refs": ["1"]},
                {"id": "Q2", "q": "托管方是谁", "state": "none", "reason": "未披露"},
            ]},
        },
    }
    if require:
        led["require_questions"] = True
    if core:
        led["core_question"] = core
    return led


GOOD_MAP = """| 格 | 题号 | 答案类型 | 报告原句 |
|---|---|---|---|
| 核心 | - | 有条件 | 该厂商或可附条件推进 |
| V/D2 | Q1 | 是 | 香港 TCSP 名册列有该主体 |
| V/D2 | Q2 | 未能核实 | 未能确认其托管方身份 |
"""


def test_complete_map_passes():
    errors, warnings = vr.check_answer_map(REPORT, _ledger(), GOOD_MAP)
    assert errors == [] and warnings == []


def test_answer_cut_from_report_is_caught():
    # 帳本已結案，成稿卻把答案刪掉：舊閘門抓不到，這條就是為它加的
    report = REPORT.replace("- **持牌**：香港 TCSP 名册列有该主体 [1]。\n", "")
    errors, _ = vr.check_answer_map(report, _ledger(), GOOD_MAP)
    assert any("not found verbatim" in e for e in errors)


def test_unmapped_ledger_question_is_caught():
    m = "\n".join(l for l in GOOD_MAP.splitlines() if "Q2" not in l)
    errors, _ = vr.check_answer_map(REPORT, _ledger(), m)
    assert any("V/D2 Q2 not mapped" in e for e in errors)


def test_open_question_is_caught():
    led = _ledger()
    led["cells"]["V/D2"]["questions"][1]["state"] = "open"
    errors, _ = vr.check_answer_map(REPORT, led, GOOD_MAP)
    assert any("still open" in e for e in errors)


def test_sourceless_question_cannot_map_to_firm_answer():
    m = GOOD_MAP.replace("| Q2 | 未能核实 |", "| Q2 | 不能 |")
    errors, _ = vr.check_answer_map(REPORT, _ledger(), m)
    assert any("closed with --none" in e for e in errors)


def test_core_answer_must_sit_on_one_line_conclusion():
    m = GOOD_MAP.replace("该厂商或可附条件推进", "香港 TCSP 名册列有该主体")
    errors, _ = vr.check_answer_map(REPORT, _ledger(), m)
    assert any("一句话结论 line" in e for e in errors)


def test_missing_core_row_and_unregistered_core():
    m = "\n".join(l for l in GOOD_MAP.splitlines() if not l.startswith("| 核心"))
    errors, _ = vr.check_answer_map(REPORT, _ledger(), m)
    assert any("no 核心 row" in e for e in errors)
    errors, _ = vr.check_answer_map(REPORT, _ledger(core=None), GOOD_MAP)
    assert any("no core question" in e for e in errors)
    errors, warnings = vr.check_answer_map(REPORT, _ledger(core=None, require=False), GOOD_MAP)
    assert errors == [] and any("legacy ledger" in w for w in warnings)


def test_bad_rows_are_caught():
    m = GOOD_MAP + "| V/D2 | Q9 | 能 | 香港 TCSP 名册列有该主体 |\n| V/D2 | Q1 | 可能 | 名册 |\n"
    errors, _ = vr.check_answer_map(REPORT, _ledger(), m)
    joined = "\n".join(errors)
    assert "unknown ledger question V/D2 Q9" in joined
    assert "'可能' not in" in joined and "too short" in joined and "duplicate row" in joined


def test_bold_and_whitespace_do_not_break_matching():
    m = GOOD_MAP.replace("香港 TCSP 名册列有该主体", "**持牌**：香港TCSP名册列有该主体")
    errors, _ = vr.check_answer_map(REPORT, _ledger(), m)
    assert errors == []


def test_cli_requires_both_flags_and_reports_failure(tmp_path):
    rpt = tmp_path / "r.md"
    rpt.write_text(REPORT, encoding="utf-8")
    led = tmp_path / "led.json"
    led.write_text(json.dumps(_ledger(), ensure_ascii=False), encoding="utf-8")
    amap = tmp_path / "map.md"
    amap.write_text(GOOD_MAP, encoding="utf-8")
    script = str(ROOT / "scripts" / "validate_report.py")
    run = lambda *a: subprocess.run([sys.executable, script, str(rpt), *a],  # noqa: E731
                                    capture_output=True, text=True)
    assert run("--answer-map", str(amap)).returncode == 2
    ok = run("--answer-map", str(amap), "--budget", str(led))
    assert ok.returncode == 0 and "mapped to report sentences" in ok.stdout
    amap.write_text(GOOD_MAP.replace("| V/D2 | Q2 | 未能核实 | 未能确认其托管方身份 |\n", ""),
                    encoding="utf-8")
    bad = run("--answer-map", str(amap), "--budget", str(led))
    assert bad.returncode == 1 and "Q2 not mapped" in bad.stdout
