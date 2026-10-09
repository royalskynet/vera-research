"""多個 deep 並行共用同一 ledger 時，每一筆花費都要記到（issue #9）。

沒有鎖時 load→modify→save 互相覆蓋：N 個並行 spend 最後只記到少於 N 筆，
預算因此少扣、上限形同虛設。
"""
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

BUDGET = Path(__file__).resolve().parents[1] / "scripts" / "budget.py"
N = 24


def test_parallel_spends_are_all_recorded(tmp_path):
    env = {**os.environ, "RESEARCH_BUDGET": str(tmp_path / "ledger.json")}

    def run(*argv):
        return subprocess.run([sys.executable, str(BUDGET), *argv], env=env, capture_output=True, text=True)

    assert run("init", "--platforms", "A", "--dims", "x", "--fetch-per-cell", "100", "--minutes", "60").returncode == 0
    assert run("ask", "A/x", "q").returncode == 0  # 過題目閘（6.5.1）
    with ThreadPoolExecutor(N) as ex:
        results = list(ex.map(lambda _: run("spend", "fetch", "A/x"), range(N)))
    ok = sum(r.stdout.startswith("OK") for r in results)
    data = json.loads((tmp_path / "ledger.json").read_text())
    assert data["cells"]["A/x"]["fetch"] == ok
    assert ok == min(N, data["total_fetch_cap"])
