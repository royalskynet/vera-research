#!/usr/bin/env python3
"""Exa 月用量警示（零 token）：當月估算花費達免費額度 80% 時通知一次（`NOTIFY_CMD` 指定通知指令，未設則印到 stdout）。

為什麼存在：Exa 免費帳號每月重置 $10（exa.ai/pricing），用完搜尋會失敗。
reach.py 每次有 key 的成功呼叫記一行到 ~/.cache/vera-research/exa-usage-YYYY-MM.tsv。
單價：MCP web_search_exa 送 type=auto＋highlights（exa-labs/exa-mcp-server
src/tools/webSearch.ts:76），REST 重放同一 body 實測 costDollars=$0.007，highlights 不另計。
可用 ?defaultSearchType=instant 降到 $0.004，但實測 top10 只重疊 5 筆、漏掉直接相關頁，不換。

ponytail: 只數 reach.py 的呼叫；agent-reach CLI 直接打 Exa 不會被算到。
要精確再改讀 Exa dashboard 的用量 API。

用法：exa_usage_watch.py [--dry]   exit 0＝未達門檻 3＝已達門檻（已通知或本月已通知過）
"""
import os
import shlex
import shutil
import subprocess
import sys
import time

USAGE_DIR = os.path.expanduser("~/.cache/vera-research")
MONTHLY_FREE = 10.0
PRICE = 0.007
THRESHOLD = 0.8


def main() -> int:
    dry = "--dry" in sys.argv[1:]
    month = time.strftime("%Y-%m")
    path = os.path.join(USAGE_DIR, f"exa-usage-{month}.tsv")
    try:
        with open(path) as f:
            calls = sum(1 for line in f if line.strip())
    except OSError:
        calls = 0
    cost = calls * PRICE
    limit_calls = int(MONTHLY_FREE * THRESHOLD / PRICE)
    print(f"exa {month}: {calls} calls ≈ ${cost:.2f} / ${MONTHLY_FREE:.0f}（80% 門檻 {limit_calls} 次）")
    if calls < limit_calls:
        return 0
    seen = os.path.join(USAGE_DIR, f"exa-usage-{month}.alerted")
    if os.path.exists(seen):
        print("本月已通知過")
        return 3
    msg = (f"[exa-usage] {month} Exa 已用 {calls} 次，估 ${cost:.2f}，達免費額度 80%。"
           f"每月 1 號重置；用完 reach.py 會改走 ddgs 備援。")
    if dry:
        print(f"(dry) 會送：{msg}")
        return 3
    notify = os.environ.get("NOTIFY_CMD")
    if notify:
        rc = subprocess.run([*shlex.split(notify), msg], capture_output=True, text=True).returncode
    else:
        print(msg)
        rc = 0
    if rc == 0:
        open(seen, "w").close()
    print(f"notify rc={rc}")
    return 3


if __name__ == "__main__":
    sys.exit(main())
