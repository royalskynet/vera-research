"""Browser cannot launch: batch stops with exit 3 and no further budget spend (not per-URL exit 2)."""
import sys
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import camofox_fetch as cf  # noqa: E402

DOWN = (500, {"error": "Camoufox version.json not found; run camoufox fetch"})


def test_browser_down_stops_batch_with_exit_3(capsys):
    spends = []
    with mock.patch.object(cf, "healthy", lambda: True), \
         mock.patch.object(cf, "_load_ledger", lambda: None), \
         mock.patch.object(cf, "_spend", lambda kind, cell, *a: spends.append(cell) or None), \
         mock.patch.object(cf, "http", lambda *a, **k: DOWN):
        rc = cf.fetch_mode(["https://a.example/", "https://b.example/", "https://c.example/"], "P/D1")
    out = capsys.readouterr().out.splitlines()
    assert rc == 3
    assert spends == ["P/D1"]  # only the first URL was charged
    assert [l.split("\t")[1] for l in out] == ["SKIP", "SKIP", "SKIP"]


def test_page_level_failure_still_exit_2():
    with mock.patch.object(cf, "healthy", lambda: True), \
         mock.patch.object(cf, "_load_ledger", lambda: None), \
         mock.patch.object(cf, "_spend", lambda *a: None), \
         mock.patch.object(cf, "http", lambda *a, **k: (400, {"error": "invalid url"})):
        assert cf.fetch_mode(["https://a.example/"], "P/D1") == 2
