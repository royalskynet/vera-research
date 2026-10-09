"""Exa 月用量：有 key 的成功呼叫才計數（匿名免費、失敗不扣額）；達 80% 只通知一次。"""
from __future__ import annotations
import json
import subprocess
import sys
import time
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import exa_usage_watch as w  # noqa: E402
import reach  # noqa: E402


def _count_after(tmp_path, key, rc):
    proc = subprocess.CompletedProcess([], rc, stdout="Title: t\nURL: https://x\n", stderr="HTTP 500")
    env = {"EXA_API_KEY": key} if key else {}
    # 必須自己寫一份「已接線」設定：不然會讀到開發機真實的 ~/.mcporter/mcporter.json，
    # 在接過線的機器上綠、在 CI 上紅（6.5.2 才暴露）。
    cfg = tmp_path / "mcporter.json"
    cfg.write_text(
        json.dumps({"mcpServers": {"exa": {"headers": {"x-api-key": "${EXA_API_KEY}"}}}}),
        encoding="utf-8",
    )
    with mock.patch.object(reach, "EXA_LOCK", str(tmp_path / "exa.lock")), \
            mock.patch.object(reach, "EXA_KEY_FILE", str(tmp_path / "none.txt")), \
            mock.patch.object(reach, "EXA_USAGE_DIR", str(tmp_path)), \
            mock.patch.object(reach, "MCPORTER_CONFIG", str(cfg)), \
            mock.patch.dict("os.environ", env, clear=True), \
            mock.patch("subprocess.run", lambda *a, **k: proc):
        reach._exa_call("m", "e")
    log = tmp_path / time.strftime("exa-usage-%Y-%m.tsv")
    return len(log.read_text().splitlines()) if log.exists() else 0


def test_keyed_success_counted(tmp_path):
    assert _count_after(tmp_path, "k", 0) == 1


def test_anonymous_and_failure_not_counted(tmp_path):
    assert _count_after(tmp_path, None, 0) == 0
    assert _count_after(tmp_path, "k", 1) == 0


def _watch(tmp_path, calls, sent):
    log = tmp_path / time.strftime("exa-usage-%Y-%m.tsv")
    log.write_text("t\tsearch\n" * calls)

    def run(argv, **k):
        sent.append(argv)
        return subprocess.CompletedProcess(argv, 0, "", "")

    with mock.patch.object(w, "USAGE_DIR", str(tmp_path)), \
            mock.patch.object(sys, "argv", ["w"]), \
            mock.patch.dict("os.environ", {"NOTIFY_CMD": "notify-test"}), \
            mock.patch("subprocess.run", run):
        return w.main()


def test_threshold_alerts_once(tmp_path):
    limit = int(w.MONTHLY_FREE * w.THRESHOLD / w.PRICE)
    sent: list = []
    assert _watch(tmp_path, limit - 1, sent) == 0 and not sent
    assert _watch(tmp_path, limit, sent) == 3 and len(sent) == 1
    assert _watch(tmp_path, limit + 50, sent) == 3 and len(sent) == 1  # 本月不重送
