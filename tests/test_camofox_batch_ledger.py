"""批次抓多個 URL 時，每頁的花費與深入輪存證都要留在 ledger 裡。

曾經的 bug：fetch_mode 在迴圈外只讀一次 ledger，每頁又把這份舊副本存回，
蓋掉上一頁由 _spend／落檔寫入的內容，導致預算少記、存證遺失。
"""
import importlib.util
import sys
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))


def _load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_batch_fetch_keeps_every_spend_and_evidence(tmp_path, monkeypatch):
    monkeypatch.setenv("RESEARCH_BUDGET", str(tmp_path / "ledger.json"))
    cf = _load("camofox_fetch")
    b = cf.budget
    assert b._capture(["init", "--platforms", "A", "--dims", "x", "--fetch-per-cell", "1"])[0] == 0
    b._capture(["spend", "fetch", "A/x"])
    b._capture(["phase", "draft"])
    assert b._capture(["phase", "deep", "--gaps", "A/x", "--fetch-per-gap", "3"])[0] == 0

    body = "China is listed as unsupported. " * 40
    with mock.patch.object(cf, "healthy", return_value=False), \
         mock.patch.object(cf, "local_python", return_value="py"), \
         mock.patch.object(cf, "local_render", return_value=("t", body)), \
         mock.patch.object(cf.time, "sleep"):
        rc = cf.fetch_mode(["https://a.test/1", "https://a.test/2", "https://a.test/3"], "A/x")

    assert rc == 0
    data = b.load(b.ledger_path())
    assert data["deep"]["used"]["A/x"]["fetch"] == 3
    assert [e["url"] for e in data["deep"]["evidence"]] == [
        "https://a.test/1", "https://a.test/2", "https://a.test/3"]
    # 第一頁的存證沒被蓋掉，才能被 verify
    assert b._capture(["verify", "A/x", "https://a.test/1", "--quote", "china is listed"])[0] == 0


def test_deep_round_may_refetch_same_url(tmp_path, monkeypatch):
    """深入輪不是「升級」：同一 URL 可重抓（例如前次正文被判擋頁），只受每格額度限制。"""
    monkeypatch.setenv("RESEARCH_BUDGET", str(tmp_path / "ledger.json"))
    cf = _load("camofox_fetch")
    b = cf.budget
    b._capture(["init", "--platforms", "A", "--dims", "x"])
    b._capture(["phase", "draft"])
    b._capture(["phase", "deep", "--gaps", "A/x", "--fetch-per-gap", "2"])
    with mock.patch.object(cf, "healthy", return_value=False), \
         mock.patch.object(cf, "local_python", return_value="py"), \
         mock.patch.object(cf, "local_render", return_value=("t", "x" * 600)):
        assert cf.fetch_mode(["https://a.test/1"], "A/x") == 0
        assert cf.fetch_mode(["https://a.test/1"], "A/x") == 0
        assert cf.fetch_mode(["https://a.test/1"], "A/x") == 4  # 額度 2 用完
