#!/usr/bin/env python3

from __future__ import annotations

import hashlib
import importlib.util
import re
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


REACH = _load("reach_test", "scripts/reach.py")
CAMOFOX = _load("camofox_fetch_test", "scripts/camofox_fetch.py")


class BlockReasonTest(unittest.TestCase):
    def test_blocked_status(self) -> None:
        self.assertEqual(REACH.block_reason(403, "x" * 600), "status")

    def test_short_body(self) -> None:
        self.assertEqual(REACH.block_reason(200, "short"), "short")

    def test_blocked_marker(self) -> None:
        self.assertEqual(REACH.block_reason(200, "Just a moment..." + "x" * 600), "marker")

    def test_clean_body(self) -> None:
        self.assertIsNone(REACH.block_reason(200, "y" * 600))


class ReadHttpErrorTest(unittest.TestCase):
    """HTTPError 無 body：只有封鎖狀態碼才升級；404 等維持 rc 2，不得誤判 short。"""

    def _read_with_code(self, code: int) -> int:
        import io
        import urllib.error
        from contextlib import redirect_stdout
        from unittest import mock

        err = urllib.error.HTTPError("https://x", code, "err", {}, None)  # type: ignore[arg-type]
        with mock.patch.object(REACH.urllib.request, "urlopen", side_effect=err), \
                mock.patch.object(REACH, "spend", return_value=None), \
                redirect_stdout(io.StringIO()):
            return REACH.read("https://x", "global")

    def test_404_stays_rc2(self) -> None:
        self.assertEqual(self._read_with_code(404), 2)

    def test_403_escalates_rc5(self) -> None:
        self.assertEqual(self._read_with_code(403), 5)


class SearchFallbackTest(unittest.TestCase):
    """Exa 失敗要改走 ddgs 而不是直接 rc3；兩邊都掛才 rc3 並退額度。"""

    def _search(self, ddgs_result):
        import io
        import subprocess
        from contextlib import redirect_stdout, redirect_stderr
        from unittest import mock

        failed = subprocess.CompletedProcess([], 1, "", "HTTP 429 rate limit")
        out = io.StringIO()
        with mock.patch.object(REACH, "spend", return_value=None), \
                mock.patch.object(REACH, "resolve_mcporter", return_value="/bin/mcporter"), \
                mock.patch.object(REACH, "_exa_call", return_value=failed), \
                mock.patch.object(REACH, "_ddgs_search", return_value=ddgs_result), \
                mock.patch.object(REACH, "refund") as refund, \
                mock.patch.object(REACH, "stamp_hits"), \
                redirect_stdout(out), redirect_stderr(io.StringIO()):
            rc, urls = REACH.search("q", "global", 5)
        return rc, urls, refund, out.getvalue()

    def test_exa_fail_uses_ddgs(self) -> None:
        rc, urls, refund, out = self._search([("T", "https://a.example")])
        self.assertEqual((rc, urls), (0, ["https://a.example"]))
        self.assertIn("T\thttps://a.example", out)
        refund.assert_not_called()

    def test_both_fail_rc3_refund(self) -> None:
        rc, urls, refund, _ = self._search(None)
        self.assertEqual((rc, urls), (3, []))
        refund.assert_called_once_with("search", "global")


class EscalationGateTest(unittest.TestCase):
    def test_first_escalation_records(self) -> None:
        data = {"cells": {"A/x": {}}}
        self.assertTrue(CAMOFOX.escalation_gate(data, "A/x", "http://u"))
        self.assertIn("http://u", data["cells"]["A/x"]["escalated"])

    def test_duplicate_escalation_skipped(self) -> None:
        data = {"cells": {"A/x": {}}}
        self.assertTrue(CAMOFOX.escalation_gate(data, "A/x", "http://u"))
        self.assertFalse(CAMOFOX.escalation_gate(data, "A/x", "http://u"))


def test_read_multi_urls(tmp_path, monkeypatch):
    calls = []

    # main 走 read_many → _fetch（平行抓取）；patch 共用接縫 _fetch，不 patch read
    def fake_fetch(url, save_dir, seq, grep):
        calls.append(url)
        return {"a": 0, "b": 2, "https://x/1": 0, "https://x/2": 3}[url], []

    monkeypatch.setattr(REACH, "_fetch", fake_fetch)
    monkeypatch.setattr(REACH, "refund", lambda *a: None)
    assert REACH.main(["read", "a", "b", "--no-budget"]) == 2
    assert sorted(calls) == ["a", "b"]

    list_file = tmp_path / "urls.txt"
    list_file.write_text("https://x/1\n\n# comment\nhttps://x/2\n", encoding="utf-8")
    calls.clear()
    assert REACH.main(["read", f"@{list_file}", "--no-budget"]) == 3
    assert sorted(calls) == ["https://x/1", "https://x/2"]


def test_read_truncated_marker(tmp_path, monkeypatch):
    import io
    from contextlib import redirect_stdout

    body = "x" * (REACH.MAX_CHARS + 100)

    class FakeResponse:
        status = 200

        def read(self):
            return body.encode("utf-8")

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(REACH.urllib.request, "urlopen", lambda *a, **k: FakeResponse())
    monkeypatch.setattr(REACH, "spend", lambda *a, **k: None)

    out = io.StringIO()
    with redirect_stdout(out):
        rc = REACH.read("https://x", "global")
    assert rc == 0
    assert "200:TRUNCATED" in out.getvalue()


def test_read_save_dir(tmp_path, monkeypatch):
    import io
    from contextlib import redirect_stdout

    body = "x" * (REACH.MAX_CHARS + 100)

    class FakeResponse:
        status = 200

        def read(self):
            return body.encode("utf-8")

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(REACH.urllib.request, "urlopen", lambda *a, **k: FakeResponse())
    monkeypatch.setattr(REACH, "spend", lambda *a, **k: None)

    out = io.StringIO()
    with redirect_stdout(out):
        rc = REACH.read("https://x", "global", save_dir=str(tmp_path), seq=0)
    assert rc == 0

    expected_name = f"0-{hashlib.sha1(b'https://x').hexdigest()[:10]}.txt"
    saved = tmp_path / expected_name
    assert saved.exists()
    assert saved.read_text(encoding="utf-8") == body

    parts = out.getvalue().strip().split("\t")
    assert parts[0] == "https://x"
    assert parts[1] == "200:TRUNCATED"
    assert parts[3] == str(saved)
    assert parts[4] == str(len(body))


def test_read_grep(tmp_path, monkeypatch):
    import io
    from contextlib import redirect_stdout

    keyword = "NEEDLE"
    body = "x" * (REACH.MAX_CHARS + 100) + " " + keyword + " tail"

    class FakeResponse:
        status = 200

        def read(self):
            return body.encode("utf-8")

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(REACH.urllib.request, "urlopen", lambda *a, **k: FakeResponse())
    monkeypatch.setattr(REACH, "spend", lambda *a, **k: None)

    out = io.StringIO()
    with redirect_stdout(out):
        rc = REACH.read("https://x", "global", grep=re.compile("needle", re.IGNORECASE))
    assert rc == 0
    value = out.getvalue()
    assert "\tGREP\t" in value
    assert keyword in value


def test_read_no_budget(tmp_path, monkeypatch):
    import io
    from contextlib import redirect_stdout

    class FakeResponse:
        status = 200

        def read(self):
            return b"x" * 600

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def fail_spend(*a, **k):
        raise AssertionError("spend should not be called with --no-budget")

    monkeypatch.setattr(REACH, "spend", fail_spend)
    monkeypatch.setattr(REACH.urllib.request, "urlopen", lambda *a, **k: FakeResponse())

    out = io.StringIO()
    with redirect_stdout(out):
        rc = REACH.main(["read", "https://x.test", "--no-budget"])
    assert rc == 0

    calls = []
    monkeypatch.setattr(REACH, "spend", lambda *a, **k: calls.append(a) or None)
    with redirect_stdout(io.StringIO()):
        rc = REACH.main(["read", "https://x.test"])
    assert rc == 0
    assert len(calls) == 1


def test_search_then_read(monkeypatch):
    import io
    from contextlib import redirect_stdout

    reads = []

    def fake_search(query, cell, max_hits):
        return 0, ["https://a.test", "https://b.test"]

    def fake_fetch(url, save_dir, seq, grep):
        reads.append(url)
        return 0, []

    monkeypatch.setattr(REACH, "search", fake_search)
    monkeypatch.setattr(REACH, "_fetch", fake_fetch)
    monkeypatch.setattr(REACH, "spend", lambda *a, **k: None)

    out = io.StringIO()
    with redirect_stdout(out):
        rc = REACH.main(["search", "q", "--read", "1"])
    assert rc == 0
    assert reads == ["https://a.test"]


if __name__ == "__main__":
    unittest.main()


def test_search_budget_denied_with_read(monkeypatch, capsys):
    # search() 的早退分支（預算拒絕／失敗）也要回 (rc, urls)；回裸 int 時
    # main 的 `rc, urls = search(...)` 會 TypeError，--read 從未跑到
    monkeypatch.setattr(REACH, "spend", lambda *a, **k: "search budget exhausted")
    reads = []
    monkeypatch.setattr(REACH, "read", lambda *a, **k: reads.append(a) or 0)
    assert REACH.main(["search", "q", "--read", "2"]) == 4
    assert reads == []
    assert "BUDGET" in capsys.readouterr().out
