#!/usr/bin/env python3
"""平行抓取的意圖：(1) 輸出順序＝輸入順序 (2) 真的平行 (3) 記帳在主執行緒依序、被拒的 URL 不抓。"""

from __future__ import annotations

import importlib.util
import io
import sys
import threading
import time
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


REACH = _load("reach_par_test", "scripts/reach.py")
VALIDATE = _load("validate_par_test", "scripts/validate_report.py")


class ReadManyTest(unittest.TestCase):
    def test_order_parallel_and_budget(self) -> None:
        fetched: list[str] = []
        spend_threads: set[str] = set()

        def fake_fetch(url, save_dir, seq, grep):
            time.sleep(0.2 if url.endswith("0") else 0.05)  # 第一個最慢，順序仍要對
            fetched.append(url)
            return 0, [f"{url}\tOK"]

        def fake_spend(kind, cell, query=None):
            spend_threads.add(threading.current_thread().name)
            return "EXHAUSTED cell=c reason=cell_cap" if calls.append(1) or len(calls) == 3 else None

        calls: list[int] = []
        urls = [f"https://h/{i}" for i in range(5)]
        buf = io.StringIO()
        t0 = time.monotonic()
        with mock.patch.object(REACH, "_fetch", side_effect=fake_fetch), \
                mock.patch.object(REACH, "spend", side_effect=fake_spend), redirect_stdout(buf):
            rc = REACH.read_many(urls, "c")
        elapsed = time.monotonic() - t0
        lines = buf.getvalue().splitlines()
        self.assertEqual([ln.split("\t")[0] for ln in lines], urls)
        self.assertIn("BUDGET", lines[2])
        self.assertNotIn("https://h/2", fetched)
        self.assertEqual(rc, 4)
        self.assertEqual(spend_threads, {"MainThread"})
        self.assertLess(elapsed, 0.35)  # 依序要 0.35s 以上


class CheckUrlsTest(unittest.TestCase):
    def test_order_kept_and_same_host_serial(self) -> None:
        active: dict[str, int] = {}
        peak: dict[str, int] = {}
        lock = threading.Lock()

        def fake_check(url, timeout=8.0):
            host = url.split("/")[2]
            with lock:
                active[host] = active.get(host, 0) + 1
                peak[host] = max(peak.get(host, 0), active[host])
            time.sleep(0.05)
            with lock:
                active[host] -= 1
            return True, url[-1]

        urls = ["https://a/1", "https://b/2", "https://a/3", "https://c/4"]
        with mock.patch.object(VALIDATE, "check_url", side_effect=fake_check):
            offline, statuses = VALIDATE.check_urls(urls)
        self.assertFalse(offline)
        self.assertEqual([s[0] for s in statuses], urls)
        self.assertEqual([s[2] for s in statuses], ["1", "2", "3", "4"])
        self.assertEqual(peak["a"], 1)


if __name__ == "__main__":
    unittest.main()
