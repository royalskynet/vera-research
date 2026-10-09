#!/usr/bin/env python3
"""Fetch pages (or run an anti-bot search) through the resident camofox-browser REST service.

Backend: camofox-browser on http://localhost:9377 (launchd com.camoufox.browser).
Only the Python standard library is used; no camoufox package is required.

Usage:
    camofox_fetch.py <URL | @urls.txt> ...          # render pages
    camofox_fetch.py --search "<query>" [--max N]    # search via @google_search macro
    [--cell <platform>/<dim>]                        # budget cell; default "global"

Output (fetch mode), one line per URL:   URL<TAB>STATUS<TAB>TITLE<TAB>BODY   (BODY newlines -> spaces)
Output (search mode), one line per hit:  TITLE<TAB>URL
Exit: 0 = all ok, 2 = at least one URL failed / no hits, 3 = service unavailable OR browser cannot
launch (/health may still say ok — browser is lazy-started; the batch stops, remaining URLs print SKIP
so no more budget is burned), 4 = budget gate

Rules: same-domain requests are spaced >= 3 s; every URL gets exactly one attempt, no retry.
"""
from __future__ import annotations

import importlib.util
import json
import os
import re
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

# budget module lives in the same scripts/ directory; imported in-process, no subprocess.
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_budget_spec = importlib.util.spec_from_file_location("budget", os.path.join(SCRIPT_DIR, "budget.py"))
_budget = importlib.util.module_from_spec(_budget_spec)
_budget_spec.loader.exec_module(_budget)
budget = _budget
# 擋頁判準唯一正本在 reach.py；深入輪落檔時沿用，不另寫一份
_reach_spec = importlib.util.spec_from_file_location("reach", os.path.join(SCRIPT_DIR, "reach.py"))
_reach = importlib.util.module_from_spec(_reach_spec)
_reach_spec.loader.exec_module(_reach)


def _ledger_exists() -> bool:
    return budget.ledger_path().exists()

BASE = "http://localhost:9377"
USER = "research"
MAX_PAGES = 5
MAX_CHARS = 20000
WAIT_TIMEOUT = 8000
SEARCH_MACRO = "@google_search"
SKIP_HOSTS = ("gstatic.", "googleapis.", "accounts.google", "support.google", "policies.google")
LINK_RE = re.compile(r'^- link "(.+?)" \[e\d+\]:?$')


def escalation_gate(data: dict, cell: str, url: str) -> bool:
    """同 URL 只升級一次：首次 True 並記入 cells[<cell>]["escalated"]，重複 False。

    URL 已含於 escalated → False（SKIP）；否則 append 並回 True。
    """
    cells = data.setdefault("cells", {})
    entry = cells.setdefault(cell, {})
    escalated = entry.setdefault("escalated", [])
    if url in escalated:
        return False
    escalated.append(url)
    return True


def http(method: str, path: str, body: dict | None = None, *, raw_query: str = "") -> tuple[int, object]:
    data = json.dumps(body).encode() if body is not None else None
    url = BASE + path + (("?" + raw_query) if raw_query else "")
    req = urllib.request.Request(url, data=data, method=method, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode("utf-8", "replace")
            try:
                return resp.status, json.loads(raw)
            except ValueError:
                return resp.status, raw
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace")
        try:
            return exc.code, json.loads(raw)
        except ValueError:
            return exc.code, raw
    except Exception as exc:  # noqa: BLE001 - network-level failure
        return 0, str(exc)


def healthy() -> bool:
    status, payload = http("GET", "/health")
    ok = status == 200 and isinstance(payload, dict) and payload.get("ok") is True
    if not ok:
        print(f"camofox service unavailable (health status={status} payload={payload})", file=sys.stderr)
    return ok


class BrowserDown(RuntimeError):
    """The service answers /health but cannot launch the browser (binary/version file missing)."""


# tool-level failure markers in the /tabs error body; a page-level failure never mentions these
BROWSER_DOWN_MARKERS = ("version", "executable", "enoent", "launch")
BROWSER_DOWN_HINT = ("camofox browser cannot launch: install @askjo/camofox-browser OUTSIDE any app's "
                     "node_modules and run `camoufox-js fetch` ; report to main session, do not retry")


def open_tab(url: str, key: str) -> str | None:
    sc, body = http("POST", "/tabs", {"userId": USER, "sessionKey": key, "url": url})
    if sc != 200 or not isinstance(body, dict) or "tabId" not in body:
        print(f"[camofox] create tab failed for {url}: {body}", file=sys.stderr)
        msg = json.dumps(body, ensure_ascii=False).lower() if not isinstance(body, str) else body.lower()
        if any(k in msg for k in BROWSER_DOWN_MARKERS):
            raise BrowserDown(msg)
        return None
    return body["tabId"]


def close_tab(tab_id: str) -> None:
    http("DELETE", f"/tabs/{tab_id}", raw_query=f"userId={USER}")


def wait_tab(tab_id: str) -> None:
    http("POST", f"/tabs/{tab_id}/wait", {"userId": USER, "timeout": WAIT_TIMEOUT, "waitForNetwork": True})


def snapshot_text(tab_id: str) -> str:
    parts: list[str] = []
    offset = 0
    for _ in range(MAX_PAGES):
        sc, snap = http("GET", f"/tabs/{tab_id}/snapshot", raw_query=f"userId={USER}&offset={offset}")
        if sc != 200 or not isinstance(snap, dict):
            break
        parts.append(snap.get("snapshot") or "")
        if not snap.get("hasMore") or snap.get("nextOffset") is None:
            break
        if (snap.get("totalChars") or 0) >= MAX_CHARS:
            break
        offset = snap["nextOffset"]
    return " ".join(parts).strip()


def page_title(tab_id: str) -> str:
    sc, res = http("POST", f"/tabs/{tab_id}/evaluate", {"userId": USER, "expression": "document.title"})
    if sc == 200 and isinstance(res, dict):
        return str(res.get("result") or "")
    return ""


# 無常駐 REST 服務的機器：CAMOUFOX_PYTHON 指向裝有 camoufox 套件的直譯器，逐頁子行程渲染
_LOCAL_RENDER = r"""
import sys, json
from camoufox.sync_api import Camoufox
with Camoufox(headless=True, humanize=True, locale="en-US") as b:
    p = b.new_page()
    p.goto(sys.argv[1], wait_until="networkidle", timeout=90000)
    p.wait_for_timeout(5000)
    print(json.dumps({"title": p.title(), "body": p.inner_text("body")}))
"""


def local_python() -> str | None:
    py = os.environ.get("CAMOUFOX_PYTHON")
    return py if py and os.path.exists(py) else None


def local_render(url: str) -> tuple[str, str]:
    import json
    import subprocess
    try:
        r = subprocess.run([local_python(), "-c", _LOCAL_RENDER, url],
                           capture_output=True, text=True, timeout=180)
        d = json.loads(r.stdout.strip().splitlines()[-1])
        return d.get("title", ""), d.get("body", "")
    except (subprocess.SubprocessError, ValueError, IndexError, OSError):
        return "", ""


# 服務端 MAX_CONCURRENT_PER_USER 預設 3（server.js:505）：同 userId 超過 3 個號誌請求會排隊 30s 後回 500
WORKERS = max(1, int(os.environ.get("CAMOFOX_WORKERS", "3")))
SAME_DOMAIN_GAP = 3.0


def _render(url: str, i: int, use_local: bool) -> tuple[str, str] | None:
    """渲染一頁回 (title, body)；開分頁失敗回 None；瀏覽器起不來拋 BrowserDown。"""
    if use_local:
        return local_render(url)
    tab_id = open_tab(url, f"fetch-{i}")
    if tab_id is None:
        return None
    wait_tab(tab_id)
    body_text = snapshot_text(tab_id)
    title = page_title(tab_id)
    close_tab(tab_id)
    return title, body_text


def fetch_mode(urls: list[str], cell: str = "global") -> int:
    """記帳在主執行緒依輸入順序做；渲染依網域分組平行（不同網域並行、同網域間隔 3 秒）。

    第一個核准的 URL 先單獨渲染當探針：瀏覽器起不來（BrowserDown）時整批停，只扣這一頁。
    """
    up = healthy()  # 只探一次：服務掛掉時第二次探測會再白等一次逾時
    use_local = not up and local_python() is not None
    if not use_local and not up:
        for u in urls:
            print(f"{u}\tSKIP\t\t")
        return 3
    out: dict[int, str] = {}
    pages: dict[int, tuple[str, str] | None] = {}
    approved: list[int] = []
    budget_hit = False
    escalate_hit = False
    probed = False
    for i, url in enumerate(urls):
        # 同 URL 只升級一次：已記過 → SKIP 並整批回 4，避免同 URL 反覆兩條通道互試。
        # 深入輪本身就是 camofox 通道、不是升級；重抓次數由 deep 每格額度限制
        with budget.ledger_lock(budget.ledger_path()):
            skip = _escalation_skip(cell, url)
        if skip:
            out[i] = f"{url}\tSKIP\t\tALREADY_ESCALATED"
            escalate_hit = True
            continue
        denied = _spend("fetch", cell)
        if denied is not None:
            out[i] = f"{url}\tBUDGET\t\t{denied}"
            budget_hit = True
            continue
        if probed:
            approved.append(i)
            continue
        probed = True
        try:
            pages[i] = _render(url, i, use_local)
        except BrowserDown:
            # stop the whole batch — every further URL would spend budget and fail the same way
            _refund(cell, url)
            for j in sorted(out):
                print(out[j])
            for rest_url in urls[i:]:
                print(f"{rest_url}\tSKIP\t\tBROWSER_DOWN")
            print(BROWSER_DOWN_HINT, file=sys.stderr)
            return 3

    groups: dict[str, list[int]] = {}
    for i in approved:
        groups.setdefault(urllib.parse.urlsplit(urls[i]).netloc, []).append(i)
    probe_domains = {urllib.parse.urlsplit(urls[i]).netloc for i in pages}
    down = threading.Event()

    def run_group(domain: str, idxs: list[int]) -> None:
        for n, i in enumerate(idxs):
            if down.is_set():
                out[i] = f"{urls[i]}\tSKIP\t\tBROWSER_DOWN"
                continue
            if n or domain in probe_domains:
                time.sleep(SAME_DOMAIN_GAP)
            try:
                pages[i] = _render(urls[i], i, use_local)
            except BrowserDown:
                down.set()
                out[i] = f"{urls[i]}\tSKIP\t\tBROWSER_DOWN"

    if groups:
        with ThreadPoolExecutor(max_workers=min(WORKERS, len(groups))) as ex:
            list(ex.map(lambda kv: run_group(*kv), groups.items()))

    for i in approved:
        if i not in pages:  # 探針後才掛：已扣額度但沒渲染
            _refund(cell, urls[i])
    failures = 0
    for i, url in enumerate(urls):
        if i in pages:
            page = pages[i]
            if page is None:
                out[i] = f"{url}\tERR\t\t"
                failures += 1
            else:
                title, body_text = page
                if not body_text:
                    failures += 1
                _save_deep_evidence(cell, url, body_text)
                status_word = "200" if body_text else "EMPTY"
                out[i] = f"{url}\t{status_word}\t{title}\t{body_text.replace(chr(10), ' ').replace(chr(13), ' ')}"
        if i in out:
            print(out[i])
    if down.is_set():
        print(BROWSER_DOWN_HINT, file=sys.stderr)
        return 3
    if budget_hit or escalate_hit:
        return 4  # budget gate / already-escalated skip outranks partial-failure exit 2
    return 2 if failures else 0


def search_mode(query: str, max_hits: int) -> int:
    if not healthy():
        return 3
    try:
        tab_id = open_tab("https://www.google.com/", "search")  # about: scheme is blocked by the service
    except BrowserDown:
        print(BROWSER_DOWN_HINT, file=sys.stderr)
        return 3
    if tab_id is None:
        return 2
    sc, res = http("POST", f"/tabs/{tab_id}/navigate", {"userId": USER, "macro": SEARCH_MACRO, "query": query})
    if sc != 200:
        print(f"[camofox] search navigate failed: {res}", file=sys.stderr)
        close_tab(tab_id)
        return 2
    wait_tab(tab_id)
    # SERP accessibility snapshot: `- link "TITLE" [eN]:` followed by `- /url: https://www.google.com/goto?url=...`
    snap = snapshot_text(tab_id)
    candidates: list[tuple[str, str]] = []
    pending_title: str | None = None
    for raw in snap.split("\n"):
        line = raw.strip()
        m = LINK_RE.match(line)
        if m:
            pending_title = m.group(1).strip()
            continue
        if pending_title and line.startswith("- /url:"):
            url = line[len("- /url:"):].strip()
            if "duckduckgo.com/y.js" in url:  # DDG 贊助廣告連結，會佔滿 --max 名額
                pending_title = None
                continue
            if url.startswith("http") and not any(h in url and "goto?url" not in url for h in SKIP_HOSTS):
                candidates.append((pending_title, url))
            pending_title = None
    seen: set[str] = set()
    hits = 0
    for title, url in candidates:
        if hits >= max_hits:
            break
        final = url
        if "google." in urllib.parse.urlsplit(url).netloc:
            # goto redirect: let the browser resolve it, read the landing URL
            sc, _ = http("POST", f"/tabs/{tab_id}/navigate", {"userId": USER, "url": url})
            if sc != 200:
                continue
            wait_tab(tab_id)
            sc, s2 = http("GET", f"/tabs/{tab_id}/snapshot", raw_query=f"userId={USER}")
            final = (s2.get("url") if sc == 200 and isinstance(s2, dict) else "") or ""
            if not final.startswith("http") or "google." in urllib.parse.urlsplit(final).netloc:
                continue
        if final in seen:
            continue
        seen.add(final)
        print(f"{title}\t{final}")
        hits += 1
    close_tab(tab_id)
    return 0 if hits else 2


def _load_ledger() -> dict | None:
    """Return current ledger dict if a budget ledger exists, else None."""
    if not _ledger_exists():
        return None
    try:
        return budget.load(budget.ledger_path())
    except (OSError, ValueError):
        # stale/corrupt ledger: do not block fetching, behave as no-ledger.
        return None


def _escalation_skip(cell: str, url: str) -> bool:
    """呼叫端須持 ledger_lock：讀→記升級→寫回是一段 RMW。"""
    ledger = _load_ledger()
    if ledger is None or ledger.get("phase") == "deep":
        return False
    if not escalation_gate(ledger, cell, url):
        return True
    budget.save(budget.ledger_path(), ledger)
    return False


def _save_deep_evidence(cell: str, url: str, body: str) -> None:
    """深入輪（phase=deep）每頁正文落檔，供 budget.py verify 逐字核對；其他階段不動。"""
    with budget.ledger_lock(budget.ledger_path()):
        data = _load_ledger()
        if data is None or data.get("phase") != "deep":
            return
        rec = budget.add_evidence(data, cell, url, body, _reach.block_reason(200, body))
        budget.save(budget.ledger_path(), data)
    if rec["block"]:
        print(f"{url}\tBLOCKED\t\t{rec['block']}", file=sys.stderr)


def _spend(kind: str, cell: str, query: str | None = None) -> str | None:
    """Try to spend one unit on (kind, cell) against the ledger.

    Returns None on success, or a budget rejection message (EXHAUSTED/HALT) to print.

    Delegates to budget.py's own spend rather than re-implementing the caps here: the
    duplicated copy silently ignored `bonus_fetch`/`bonus_search`, so a `budget.py topup`
    raised the quota for reach.py but not for this script.
    """
    if _load_ledger() is None:
        return None  # no ledger -> unlimited (identical to current behaviour)
    argv = ["spend", kind, cell, "--channel", "camofox"]
    if query:
        argv += ["--q", query]
    code, out = budget._capture(argv)
    if code == 0:
        return None
    msg = out.strip().splitlines()[-1] if out.strip() else ""
    return msg or f"EXHAUSTED cell={cell}"


def _refund(cell: str, url: str) -> None:
    """瀏覽器起不來（沒渲染）的頁退回額度並撤銷升級標記，之後可重試；只在主執行緒呼叫。"""
    if _load_ledger() is None:
        return
    with budget.ledger_lock(budget.ledger_path()):
        data = _load_ledger()
        esc = (data or {}).get("cells", {}).get(cell, {}).get("escalated", [])
        if url in esc:
            esc.remove(url)
            budget.save(budget.ledger_path(), data)
        budget._capture(["refund", "fetch", cell, "--channel", "camofox"])


def main() -> int:
    argv = sys.argv[1:]
    cell = "global"
    # extract optional --cell <val> anywhere in argv; remaining parse unchanged
    rest: list[str] = []
    it = iter(argv)
    for a in it:
        if a == "--cell":
            try:
                cell = next(it)
            except StopIteration:
                print("usage: --cell <platform>/<dim>", file=sys.stderr)
                return 2
        else:
            rest.append(a)
    if not rest:
        print(__doc__, file=sys.stderr)
        return 2
    if rest[0] == "--search":
        if len(rest) < 2:
            print("usage: camofox_fetch.py --search \"<query>\" [--max N]", file=sys.stderr)
            return 2
        query = rest[1]
        max_hits = 10
        if "--max" in rest:
            try:
                max_hits = int(rest[rest.index("--max") + 1])
            except (IndexError, ValueError):
                pass
        # budget gate runs BEFORE healthy() (offline-testable)
        denied = _spend("search", cell, query)
        if denied is not None:
            print(f"BUDGET\t{denied}")
            return 4
        return search_mode(query, max_hits)

    urls: list[str] = []
    for arg in rest:
        if arg.startswith("@"):
            try:
                with open(arg[1:], encoding="utf-8") as fh:
                    urls.extend(l.strip() for l in fh if l.strip() and not l.lstrip().startswith("#"))
            except OSError as exc:
                print(f"ERR cannot read {arg}: {exc}", file=sys.stderr)
                return 2
        else:
            urls.append(arg)
    if not urls:
        print("no URLs to fetch", file=sys.stderr)
        return 2
    return fetch_mode(urls, cell)


if __name__ == "__main__":
    raise SystemExit(main())
