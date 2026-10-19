"""背景調研只給「较为建议／较不建议」：審批措辭（附条件推进等）必須被禁詞閘門擋下，傾向詞本身不得誤擋。"""
import re
from pathlib import Path

FW = Path(__file__).resolve().parents[1] / "references" / "forbidden-words.md"


def _patterns():
    text = FW.read_text(encoding="utf-8")
    block = re.search(r"^```text\n(.*?)^```$", text, re.S | re.M).group(1)
    return [re.compile(p.strip()) for p in block.splitlines() if p.strip()]


def _hits(s):
    return [p.pattern for p in _patterns() if p.search(s)]


def test_approval_wording_is_blocked():
    for s in ("结论倾向：或可附条件推进。", "不推荐无条件推进", "或可暂缓合作", "或可推进"):
        assert _hits(s), s


def test_tendency_wording_passes():
    assert _hits("结论倾向：较不建议。VARA 于 2026-06-22 处以罚款 [12]。") == []
    assert _hits("结论倾向：较为建议。") == []
