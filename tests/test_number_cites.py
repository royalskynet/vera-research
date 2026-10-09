"""Draft tags -> sequential [N]: first-appearance order, URL dedup, missing tag reported."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import number_cites as nc  # noqa: E402

ROW = "| {rid} | {g} | {t} | {u} | 2026-09-28 | 2026-07-13 | 摘錄 | Q1 |"


def test_numbering_dedup_and_missing(tmp_path):
    d1 = tmp_path / "D1.md"
    d1.write_text("\n".join([
        "| 編號 | 等級 | 標題 | URL | 查閱日期 | 頁面日期 | 摘錄 | 支持 |",
        ROW.format(rid="R1", g="S1", t="AMF", u="https://a.example/x"),
        ROW.format(rid="R2", g="S2", t="Terms", u="https://b.example/t/"),
    ]), encoding="utf-8")
    x = tmp_path / "sources.md"
    x.write_text(ROW.format(rid="R1", g="S2", t="Terms again", u="https://b.example/t"), encoding="utf-8")

    draft = "第二 [D1R2] 第一 [D1R1][D1R1] 同URL [XR1] 缺 [D9R7]\n\n<<SOURCES>>\n"
    body, order, missing = nc.number(draft, nc.load_sources([d1, x]))

    assert body.startswith("第二 [1] 第一 [2] 同URL [1] 缺 [3]")
    assert order == ["D1R2", "D1R1", "D9R7"]
    assert missing == ["D9R7"]
    assert "| 1 | Terms | S2 | https://b.example/t/ |" in body
    assert "| 3 | D9R7 | ? |" in body
