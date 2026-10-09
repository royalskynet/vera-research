"""匿名 Exa 免費 MCP 會 429：_exa_call 要退避重試，非 429 失敗不重試。

槽位數只認「金鑰真的會被送到 Exa」（環境變數／key 檔 **且** mcporter exa entry 帶 x-api-key
header）。金鑰有值但 header 未接時維持單路並出聲一次——見 test_unwired_key_stays_serialised。
"""
from __future__ import annotations
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import reach  # noqa: E402


def _proc(rc, err=""):
    return subprocess.CompletedProcess([], rc, stdout="" if rc else "Title: t\nURL: https://x\n", stderr=err)


def test_429_retried_until_success(tmp_path):
    seq = iter([_proc(1, "HTTP 429 You've hit Exa's free MCP rate limit"), _proc(0)])
    with mock.patch.object(reach, "EXA_LOCK", str(tmp_path / "exa.lock")), \
            mock.patch.object(reach, "EXA_BACKOFF", (0, 0)), \
            mock.patch("subprocess.run", lambda *a, **k: next(seq)) as _:
        assert reach._exa_call("mcporter", "expr").returncode == 0


def test_non_ratelimit_failure_not_retried(tmp_path):
    calls = []

    def run(*a, **k):
        calls.append(1)
        return _proc(1, "HTTP 500 boom")

    with mock.patch.object(reach, "EXA_LOCK", str(tmp_path / "exa.lock")), \
            mock.patch.object(reach, "EXA_BACKOFF", (0, 0)), \
            mock.patch("subprocess.run", run):
        assert reach._exa_call("mcporter", "expr").returncode == 1
    assert len(calls) == 1


def _peak_concurrency(tmp_path, key: str | None, wired: bool) -> int:
    """8 條執行緒同時呼叫 _exa_call，回傳同時在 subprocess.run 裡的最大數。

    `wired` 決定 mcporter 的 exa entry 是否帶 x-api-key header —— 槽位數只認「金鑰真的
    會被送到 Exa」，所以這必須能獨立於環境變數控制。
    """
    import threading
    import time

    live, peak, mu = [0], [0], threading.Lock()

    def run(*a, **k):
        with mu:
            live[0] += 1
            peak[0] = max(peak[0], live[0])
        time.sleep(0.15)
        with mu:
            live[0] -= 1
        return _proc(0)

    env = {"EXA_API_KEY": key} if key else {}
    cfg = tmp_path / "mcporter.json"
    cfg.write_text(
        json.dumps({"mcpServers": {"exa": {"headers": {"x-api-key": "${EXA_API_KEY}"}}}})
        if wired else json.dumps({"mcpServers": {"exa": {"baseUrl": "https://mcp.exa.ai/mcp"}}}),
        encoding="utf-8",
    )
    with mock.patch.object(reach, "EXA_LOCK", str(tmp_path / "exa.lock")), \
            mock.patch.object(reach, "EXA_KEY_FILE", str(tmp_path / "none.txt")), \
            mock.patch.object(reach, "EXA_USAGE_DIR", str(tmp_path)), \
            mock.patch.object(reach, "MCPORTER_CONFIG", str(cfg)), \
            mock.patch.object(reach, "_UNWIRED_KEY_NOTICE", object()), \
            mock.patch.dict("os.environ", env, clear=True), \
            mock.patch("subprocess.run", run):
        ts = [threading.Thread(target=reach._exa_call, args=("m", "e")) for _ in range(8)]
        for t in ts:
            t.start()
        for t in ts:
            t.join()
    return peak[0]


def test_wired_key_allows_parallel_slots(tmp_path):
    assert 1 < _peak_concurrency(tmp_path, "k", wired=True) <= reach.EXA_SLOTS_KEYED


def test_unwired_key_stays_serialised(tmp_path):
    """金鑰有值但 header 沒接 → 維持單路。這是 6.4.7 靜默失效的根因迴歸測試。"""
    assert _peak_concurrency(tmp_path, "k", wired=False) == 1


def test_anonymous_serialised(tmp_path):
    assert _peak_concurrency(tmp_path, None, wired=False) == 1


def test_key_resolves_from_file_when_env_absent(tmp_path):
    key_file = tmp_path / "k.txt"
    key_file.write_text("secret\n", encoding="utf-8")
    with mock.patch.object(reach, "EXA_KEY_FILE", str(key_file)), \
            mock.patch.dict("os.environ", {}, clear=True):
        assert reach._exa_key({}) == "secret"


def test_key_missing_returns_none(tmp_path):
    with mock.patch.object(reach, "EXA_KEY_FILE", str(tmp_path / "none.txt")), \
            mock.patch.dict("os.environ", {}, clear=True):
        assert reach._exa_key({}) is None


class HeaderProbeTest(unittest.TestCase):
    """_mcporter_exa_headers：壞掉的設定檔不得讓 keyed 判定誤判為有接線。"""

    def _cfg(self, tmp_dir: Path, body: str) -> str:
        p = tmp_dir / "mcporter.json"
        p.write_text(body, encoding="utf-8")
        return str(p)

    def _headers(self, tmp_dir: Path, body: str) -> dict:
        with mock.patch.object(reach, "MCPORTER_CONFIG", self._cfg(tmp_dir, body)):
            return reach._mcporter_exa_headers()

    def test_absent_file_is_unwired(self):
        with tempfile.TemporaryDirectory() as d:
            with mock.patch.object(reach, "MCPORTER_CONFIG", str(Path(d) / "none.json")):
                self.assertEqual(reach._mcporter_exa_headers(), {})

    def test_malformed_json_is_unwired(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(self._headers(Path(d), "{not json"), {})

    def test_no_exa_entry_is_unwired(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(self._headers(Path(d), '{"mcpServers":{}}'), {})

    def test_headers_not_dict_is_unwired(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(self._headers(Path(d), json.dumps({"mcpServers": {"exa": {"headers": ["x-api-key"]}}})), {})

    def test_header_name_is_case_insensitive(self):
        with tempfile.TemporaryDirectory() as d:
            body = json.dumps({"mcpServers": {"exa": {"headers": {"X-API-Key": "${EXA_API_KEY}"}}}})
            self.assertIn("x-api-key", self._headers(Path(d), body))


def test_unwired_key_warns_once(tmp_path, capsys):
    """金鑰形同未設要出聲，且只出一次——每次呼叫都噴會淹掉 ledger 輸出。"""
    import threading

    cfg = tmp_path / "mcporter.json"
    cfg.write_text(json.dumps({"mcpServers": {"exa": {}}}), encoding="utf-8")
    notice = "金鑰形同未設"
    with mock.patch.object(reach, "MCPORTER_CONFIG", str(cfg)), \
            mock.patch.object(reach, "EXA_KEY_FILE", str(tmp_path / "none.txt")), \
            mock.patch.object(reach, "_UNWIRED_KEY_NOTICE", notice), \
            mock.patch.dict("os.environ", {"EXA_API_KEY": "k"}, clear=True):
        ts = [threading.Thread(target=reach._warn_header_unwired) for _ in range(4)]
        for t in ts:
            t.start()
        for t in ts:
            t.join()
    assert capsys.readouterr().err.count(notice) == 1

