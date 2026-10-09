"""同一報告目錄開第二本帳做補證時，深入輪存證不得覆蓋第一本帳的檔案。

曾經的 bug：存證檔名只用帳內序號（001.txt…），新帳從 001 重來，
蓋掉舊帳同名存證，舊帳 verify 讀到的就不是當初抓的正文。
"""
import importlib.util
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def _budget():
    spec = importlib.util.spec_from_file_location("budget", SCRIPTS / "budget.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_second_ledger_does_not_overwrite_first_ledger_evidence(tmp_path, monkeypatch):
    b = _budget()
    paths = []
    for name, body in (("ledger-a.json", "first ledger page"), ("ledger-b.json", "second ledger page")):
        monkeypatch.setenv("RESEARCH_BUDGET", str(tmp_path / name))
        data = {"deep": {"evidence": []}}
        paths.append(Path(b.add_evidence(data, "A/x", "https://a.test", body, None)["path"]))
    assert paths[0] != paths[1]
    assert paths[0].read_text(encoding="utf-8") == "first ledger page"
