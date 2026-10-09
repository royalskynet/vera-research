"""camofox 批次抓取：不同網域並行渲染、同網域維持間隔、輸出照輸入順序。

意圖：深入輪每頁本機渲染 95–180 秒，序列跑一個缺口 4 頁就要 6–12 分鐘；
並行不能打亂輸出順序（呼叫端靠行序對應 URL），也不能讓同網域連打觸發反爬。
"""
import sys
import threading
import time
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import camofox_fetch as cf  # noqa: E402


def _run(urls, render):
    with mock.patch.object(cf, "healthy", lambda: True), \
         mock.patch.object(cf, "_load_ledger", lambda: None), \
         mock.patch.object(cf, "_spend", lambda *a: None), \
         mock.patch.object(cf, "_render", render), \
         mock.patch.object(cf, "SAME_DOMAIN_GAP", 0.0):
        return cf.fetch_mode(urls, "P/D1")


def test_distinct_domains_render_concurrently_and_keep_order(capsys):
    live, peak, lock = [0], [0], threading.Lock()

    def render(url, i, use_local):
        with lock:
            live[0] += 1
            peak[0] = max(peak[0], live[0])
        time.sleep(0.2)
        with lock:
            live[0] -= 1
        return "t", f"body-{url}"

    urls = ["https://p.test/", "https://a.test/", "https://b.test/", "https://c.test/"]
    assert _run(urls, render) == 0
    lines = capsys.readouterr().out.splitlines()
    assert [l.split("\t")[0] for l in lines] == urls
    assert peak[0] == 3  # 探針後 3 個網域同時跑，不超過 WORKERS


def test_same_domain_stays_serial():
    live, peak, lock = [0], [0], threading.Lock()

    def render(url, i, use_local):
        with lock:
            live[0] += 1
            peak[0] = max(peak[0], live[0])
        time.sleep(0.05)
        with lock:
            live[0] -= 1
        return "t", "body"

    assert _run([f"https://a.test/{n}" for n in range(4)], render) == 0
    assert peak[0] == 1


def _fresh(tmp_path, monkeypatch):
    import importlib.util
    monkeypatch.setenv("RESEARCH_BUDGET", str(tmp_path / "ledger.json"))
    spec = importlib.util.spec_from_file_location("cf2", Path(cf.__file__))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.budget._capture(["init", "--platforms", "A", "--dims", "x"])
    mod.budget._capture(["phase", "draft"])
    return mod


def _down_after_ok(mod):
    def render(url, i, use_local):
        if url.endswith("/ok"):
            return "t", "body"
        raise mod.BrowserDown("gone")
    return render


def test_browser_down_mid_batch_refunds_deep(tmp_path, monkeypatch):
    """探針成功後瀏覽器才掛：沒渲染的頁退回深入輪額度，只留成功那頁的花費。"""
    mod = _fresh(tmp_path, monkeypatch)
    b = mod.budget
    b._capture(["phase", "deep", "--gaps", "A/x", "--fetch-per-gap", "3"])
    with mock.patch.object(mod, "healthy", lambda: True), \
         mock.patch.object(mod, "_render", _down_after_ok(mod)), \
         mock.patch.object(mod, "SAME_DOMAIN_GAP", 0.0):
        rc = mod.fetch_mode(["https://a.test/ok", "https://b.test/x", "https://c.test/y"], "A/x")
    assert rc == 3
    assert b.load(b.ledger_path())["deep"]["used"]["A/x"]["fetch"] == 1


def test_browser_down_probe_refunds_and_unmarks_escalation(tmp_path, monkeypatch):
    """第二輪升級時瀏覽器起不來：額度退回、升級標記撤銷，否則同 URL 之後永遠 ALREADY_ESCALATED。"""
    mod = _fresh(tmp_path, monkeypatch)
    b = mod.budget
    b._capture(["phase", "round2", "--gaps", "A/x"])
    with mock.patch.object(mod, "healthy", lambda: True), \
         mock.patch.object(mod, "_render", _down_after_ok(mod)):
        assert mod.fetch_mode(["https://b.test/x"], "A/x") == 3
    c = b.load(b.ledger_path())["cells"]["A/x"]
    assert c.get("r2c_fetch", 0) == 0
    assert "https://b.test/x" not in c.get("escalated", [])
