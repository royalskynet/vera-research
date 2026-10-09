#!/usr/bin/env python3
"""reach.py — agent-reach glue for the research skill, with budget accounting.

Usage:
    reach.py search "<query>" [--cell <platform>/<dim>] [--max 5] [--read N]
        Exa web search via `mcporter call 'exa.web_search_exa(...)'`. Prints one hit per line: TITLE\\tURL
        If Exa fails (mcporter missing / timeout / error after 429 retries), falls back to ddgs via a
        one-shot `uvx --from ddgs` process (no daemon); rc=3 + refund only when both fail.
        With --read N, the first N hits are then read via read() (one fetch each); rc = max of search/reads.
    reach.py read <URL>... [--cell <platform>/<dim>] [--save-dir DIR]
        Jina Reader (https://r.jina.ai/<URL>). Prints one line: URL\\tSTATUS\\tTITLE\\tBODY (BODY <= 20000 chars; STATUS gets :TRUNCATED when cut)
        Accepts multiple URLs and @<file> (one URL per line, blank/# lines skipped); exit code = max of per-URL rc.
        Multiple URLs: budget is spent serially first, then pages are fetched READ_WORKERS at a time; output keeps input order.
        With --save-dir, full body is saved to DIR/<seq>-<sha1(url)[:10]>.txt; stdout prints URL\\tSTATUS\\tTITLE\\tPATH\\tCHARS.
        With --grep <regex>, each successful read also prints up to 20 \\tGREP\\t<80 chars before/after match> lines from the full untruncated body.
        With --no-budget, reads skip budget accounting (liveness checks when finalising a report).

Trail: every search records its query into `cells[<cell>].queries[]` (query/time/hit count,
-1 = the search itself failed) so a negative claim in the report can be audited against what was
actually run. check_report.sh fails any report that states "not found" without such a trail.

Keyed mode: EXA_API_KEY (or ~/.config/vera-research/EXA_API_KEY.txt) only reaches Exa if mcporter's exa entry
carries the `x-api-key` header. When it does, searches run 5-wide; when it does not, they stay
serialised (the anonymous free tier 429s at 5) and a one-shot notice prints the fix command.

Budget: when a ledger exists (`$RESEARCH_BUDGET` or ./.research-budget.json, see budget.py) every search
spends one `search` unit and every read spends one `fetch` unit on --cell (default "global") BEFORE any
network call. A refused spend prints BUDGET and exits 4. Without a ledger nothing is recorded.

Exit codes: 0 ok | 2 no results / HTTP failure | 3 tool unavailable (mcporter missing, timeout, network) | 4 budget gate | 5 blocked page (STATUS=BLOCKED:<reason>)
"""
from __future__ import annotations

import glob
import hashlib
import importlib.util
import json
import os
import re
import shutil
import ssl
import subprocess
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
MAX_CHARS = 20000
READ_TIMEOUT = 30
READ_WORKERS = 4
SEARCH_TIMEOUT = 60
JINA = "https://r.jina.ai/"
MCPORTER_INSTALL_HINT = "install: `npm i -g mcporter` (nvm-safe; no admin needed)"

# 擋頁標記：命中即視為反爬／登入／cookie 牆。借鏡 gpt-researcher／crawl4ai 的擋頁標記。
BLOCKED_MARKER_RE = re.compile(
    r"just a moment|attention required|enable javascript|access denied|captcha|"
    r"verify you are human|please log in|sign in to continue|accept all cookies|"
    r"datadome|akamai|incapsula|perimeterx",
    re.IGNORECASE,
)
BLOCKED_STATUSES = (401, 403, 429, 503)


def block_reason(status: int, body: str) -> str | None:
    """機械判「退 camofox」：status 封鎖碼 → 短內文 → 擋頁標記，否則 None。

    順序固定 status→short→marker。500 閾值與既有 rc 語意不得改動。
    """
    if status in BLOCKED_STATUSES:
        return "status"
    if len(body) < 500:
        return "short"
    if BLOCKED_MARKER_RE.search(body[:3000]):
        return "marker"
    return None


EXA_LOCK = os.path.expanduser("~/.cache/vera-research/exa.lock")
EXA_BACKOFF = (3, 8)  # 秒；429 後重試間隔
EXA_KEY_FILE = os.environ.get("EXA_KEY_FILE") or os.path.expanduser("~/.config/vera-research/EXA_API_KEY.txt")
EXA_SLOTS_KEYED = 5  # 有 key：官方 /search 10 QPS，5 路留餘裕
EXA_SLOTS_ANON = 1   # 匿名免費 MCP：8 並發實測 5 個 429
EXA_USAGE_DIR = os.path.expanduser("~/.cache/vera-research")  # exa-usage-YYYY-MM.tsv，exa_usage_watch.py 讀
MCPORTER_CONFIG = os.path.expanduser("~/.mcporter/mcporter.json")
EXA_HEADER = "x-api-key"
# 值用 ${EXA_API_KEY} 佔位 → 密鑰不落設定檔，由 _exa_env() 注入子行程 env。
EXA_HEADER_FIX = (
    "mcporter config add exa --url https://mcp.exa.ai/mcp "
    "--header 'x-api-key=${EXA_API_KEY}' --scope home"
)


def _exa_count() -> None:
    """有 key 的成功呼叫記一行，供月用量警示；失敗不影響搜尋。"""
    import time
    try:
        path = os.path.join(EXA_USAGE_DIR, time.strftime("exa-usage-%Y-%m.tsv"))
        with open(path, "a") as f:
            f.write(time.strftime("%Y-%m-%dT%H:%M:%S") + "\tsearch\n")
    except OSError:
        pass


def _exa_key(env: dict) -> str | None:
    """金鑰值：環境變數優先，其次讀 key 檔。回 None＝無金鑰。"""
    if env.get("EXA_API_KEY"):
        return env["EXA_API_KEY"]
    try:
        with open(EXA_KEY_FILE) as f:
            return f.read().strip() or None
    except OSError:
        return None


def _mcporter_exa_headers() -> dict:
    """`~/.mcporter/mcporter.json` 裡 mcpServers.exa.headers，key 一律小寫。

    設定檔不存在／不是合法 JSON／無 exa entry／headers 非 dict → {}（視為未接線）。
    """
    try:
        with open(MCPORTER_CONFIG) as f:
            cfg = json.load(f)
    except (OSError, ValueError):
        return {}
    entry = (cfg.get("mcpServers") or {}).get("exa") or {}
    headers = entry.get("headers") if isinstance(entry, dict) else None
    if not isinstance(headers, dict):
        return {}
    return {str(k).lower(): str(v) for k, v in headers.items()}


_UNWIRED_KEY_NOTICE = (
    "EXA_API_KEY 有值，但不會送到 Exa：mcporter 的 exa entry 沒有 "
    f"{EXA_HEADER} header。已維持單路（匿名限流），否則多路只會換來 429。"
    f"\n修復（一次性）：{EXA_HEADER_FIX}"
)


def _warn_header_unwired() -> None:
    """金鑰形同未設時出聲一次；不中斷流程，只是不再假裝自己已接線。"""
    global _UNWIRED_KEY_NOTICE
    if _UNWIRED_KEY_NOTICE:
        print(f"[reach] {_UNWIRED_KEY_NOTICE}", file=sys.stderr)
        _UNWIRED_KEY_NOTICE = None


def _exa_env() -> tuple[dict, int]:
    """子行程 env ＋ 並發槽位數。金鑰注入子行程，值不落 stdout。

    槽位數只認「金鑰真的會被送到 Exa」：key 有值 **且** mcporter 的 exa entry 帶
    `x-api-key` header。缺 header 時金鑰形同未設，多開槽位只會把匿名免費額度打成 429。
    """
    env = dict(os.environ)
    key = _exa_key(env)
    if key:
        env["EXA_API_KEY"] = key
        if EXA_HEADER in _mcporter_exa_headers():
            return env, EXA_SLOTS_KEYED
        _warn_header_unwired()
    return env, EXA_SLOTS_ANON


def _exa_call(mcporter: str, expr: str) -> subprocess.CompletedProcess:
    """跨行程檔案鎖限制 Exa 同時呼叫數（已接線 5 路／未接線 1 路）＋429 退避。"""
    import fcntl
    import time

    env, slots = _exa_env()
    os.makedirs(os.path.dirname(EXA_LOCK), exist_ok=True)
    lock = None
    while lock is None:  # 搶任一個 slot 鎖；全滿就短睡再搶
        for i in range(slots):
            f = open(f"{EXA_LOCK}.{i}", "w")
            try:
                fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
                lock = f
                break
            except OSError:
                f.close()
        if lock is None:
            time.sleep(0.2)
    with lock:
        for wait in (*EXA_BACKOFF, None):
            proc = subprocess.run([mcporter, "call", expr], capture_output=True, text=True,
                                  timeout=SEARCH_TIMEOUT, env=env)
            limited = proc.returncode != 0 and ("429" in proc.stderr or "rate limit" in proc.stderr)
            if not limited or wait is None:
                if slots == EXA_SLOTS_KEYED and proc.returncode == 0:
                    _exa_count()
                return proc
            print(f"[reach] exa rate-limited; retry in {wait}s", file=sys.stderr)
            time.sleep(wait)
    return proc


DDGS_SNIPPET = "import json,sys; from ddgs import DDGS; print(json.dumps(DDGS().text(sys.argv[1], max_results=int(sys.argv[2]))))"


def _ddgs_search(query: str, max_hits: int) -> list[tuple[str, str]] | None:
    """Exa 失敗時的備援：`uvx --from ddgs` 單次行程（搜完即退，不常駐、無 docker）。

    回 None＝備援本身不可用（沒 uvx／逾時／非 JSON）；回 []＝跑了但沒結果。
    """
    uvx = shutil.which("uvx") or os.path.expanduser("~/.local/bin/uvx")
    if not os.access(uvx, os.X_OK):
        return None
    try:
        proc = subprocess.run([uvx, "--from", "ddgs", "python", "-c", DDGS_SNIPPET, query, str(max_hits)],
                              capture_output=True, text=True, timeout=SEARCH_TIMEOUT)
        rows = json.loads(proc.stdout or "null")
    except (subprocess.TimeoutExpired, ValueError):
        return None
    if not isinstance(rows, list):
        return None
    return [(r.get("title", ""), r["href"]) for r in rows if str(r.get("href", "")).startswith("http")]


def resolve_mcporter() -> str | None:
    """Return path to mcporter, checking PATH plus common nvm/npm-global locations."""
    hit = shutil.which("mcporter")
    if hit:
        return hit
    for pattern in (
        os.path.expanduser("~/.nvm/versions/node/*/bin/mcporter"),
        os.path.expanduser("~/.local/bin/mcporter"),
        os.path.expanduser("~/.npm-global/bin/mcporter"),
    ):
        for candidate in sorted(glob.glob(pattern), reverse=True):
            if os.access(candidate, os.X_OK):
                return candidate
    return None

_spec = importlib.util.spec_from_file_location("budget", os.path.join(SCRIPT_DIR, "budget.py"))
budget = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(budget)


def spend(kind: str, cell: str, query: str | None = None) -> str | None:
    """Return None when allowed (or no ledger); otherwise the refusal message."""
    if not budget.ledger_path().exists():
        return None
    argv = ["spend", kind, cell]
    if query:
        argv += ["--q", query]
    code, out = budget._capture(argv)
    return None if code == 0 else out.strip().splitlines()[-1] if out.strip() else f"EXHAUSTED cell={cell}"


def refund(kind: str, cell: str) -> None:
    """工具不可用（rc=3）退回剛扣的額度；沒有 ledger 就什麼都不做。"""
    if budget.ledger_path().exists():
        budget._capture(["refund", kind, cell])


def stamp_hits(cell: str, hits: int) -> None:
    """把命中數回填到剛記下的查詢；沒有 ledger 就什麼都不做。"""
    if budget.ledger_path().exists():
        budget._capture(["trail", cell, "--hits", str(hits)])


def search(query: str, cell: str, max_hits: int) -> tuple[int, list[str]]:
    denied = spend("search", cell, query)
    if denied:
        print(f"BUDGET\t{denied}")
        return 4, []
    mcporter = resolve_mcporter()
    failure: str | None = None
    proc = None
    if mcporter is None:
        failure = f"mcporter not found; {MCPORTER_INSTALL_HINT}"
    else:
        q = query.replace('"', "'")
        expr = f'exa.web_search_exa(query: "{q}", numResults: {max_hits})'
        try:
            proc = _exa_call(mcporter, expr)
            if proc.returncode != 0 and not proc.stdout.strip():
                failure = f"mcporter failed: {proc.stderr.strip()[:200]}"
        except subprocess.TimeoutExpired:
            failure = "mcporter timeout"
    if failure:
        print(f"[reach] {failure}; falling back to ddgs", file=sys.stderr)
        fallback = _ddgs_search(query, max_hits)
        if fallback is None:
            stamp_hits(cell, -1)
            print("[reach] ddgs fallback unavailable", file=sys.stderr)
            refund("search", cell)
            return 3, []
        stamp_hits(cell, len(fallback))
        for t, u in fallback:
            print(f"{t}\t{u}")
        return (0 if fallback else 2), [u for _, u in fallback]
    hits: list[tuple[str, str]] = []
    seen: set[str] = set()
    title: str | None = None
    for raw in proc.stdout.splitlines():
        line = raw.strip()
        if line.startswith("Title:"):
            title = line[len("Title:"):].strip()
        elif line.startswith("URL:"):
            url = line[len("URL:"):].strip()
            if url.startswith("http") and url not in seen:
                seen.add(url)
                hits.append((title or "", url))
            title = None
        if len(hits) >= max_hits:
            break
    stamp_hits(cell, len(hits))
    for t, u in hits:
        print(f"{t}\t{u}")
    return (0 if hits else 2), [u for _, u in hits]


_HEADER_PREFIXES = ("Title:", "URL Source:", "Published Time:", "Warning:", "Markdown Content:")


def _ssl_context() -> ssl.SSLContext | None:
    """Honour SSL_CERT_FILE / REQUESTS_CA_BUNDLE.

    A MITM proxy (sandbox, corp egress) injects its own root; urllib reads the system
    trust store only, so every read died with a bare CERTIFICATE_VERIFY_FAILED while curl
    on the same URL returned 200.
    """
    ca = os.environ.get("SSL_CERT_FILE") or os.environ.get("REQUESTS_CA_BUNDLE")
    if not ca or not os.path.exists(ca):
        return None
    try:
        return ssl.create_default_context(cafile=ca)
    except (OSError, ssl.SSLError):
        return None


def read(url: str, cell: str, save_dir: str | None = None, seq: int = 0, grep: re.Pattern | None = None, budget: bool = True) -> int:
    if budget:
        denied = spend("fetch", cell)
        if denied:
            print(f"{url}\tBUDGET\t\t{denied}")
            return 4
    rc, lines = _fetch(url, save_dir, seq, grep)
    if rc == 3 and budget:
        refund("fetch", cell)
    for line in lines:
        print(line)
    return rc


def read_many(urls: list[str], cell: str, save_dir: str | None = None, grep: re.Pattern | None = None,
              budget: bool = True) -> int:
    """多 URL：主執行緒依序記帳（budget 的 flock 重入計數是行程全域，不可多執行緒進入），
    網路抓取平行，輸出維持輸入順序。"""
    results: list[tuple[int, list[str]] | None] = [None] * len(urls)
    todo: list[int] = []
    for i, url in enumerate(urls):
        denied = spend("fetch", cell) if budget else None
        if denied:
            results[i] = (4, [f"{url}\tBUDGET\t\t{denied}"])
        else:
            todo.append(i)
    # ponytail: 固定 4 條；Jina 免 key 限 20 RPM，再多會換來 429→BLOCKED。有 JINA key 再調高
    with ThreadPoolExecutor(max_workers=READ_WORKERS) as pool:
        futs = {i: pool.submit(_fetch, urls[i], save_dir, i, grep) for i in todo}
        for i, fut in futs.items():
            results[i] = fut.result()
            if results[i][0] == 3 and budget:
                refund("fetch", cell)  # 主執行緒記帳，同 spend
    rc = 0
    for r in results:
        assert r is not None
        rc = max(rc, r[0])
        for line in r[1]:
            print(line)
    return rc


def _fetch(url: str, save_dir: str | None, seq: int, grep: re.Pattern | None) -> tuple[int, list[str]]:
    """抓一頁並組好輸出行；不記帳、不 print，可在執行緒內跑。"""
    out: list[str] = []
    req = urllib.request.Request(
        JINA + url,
        headers={"User-Agent": "research-skill/5.1", "Accept": "text/plain"},
    )
    try:
        with urllib.request.urlopen(req, timeout=READ_TIMEOUT, context=_ssl_context()) as resp:
            status = resp.status
            text = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        # HTTPError 沒有 body 可判，只看狀態碼；否則 404／500 會因空 body 被誤判 short。
        if exc.code in BLOCKED_STATUSES:
            return 5, [f"{url}\tBLOCKED:status\t\t"]
        return 2, [f"{url}\t{exc.code}\t\t"]
    except Exception as exc:  # noqa: BLE001 - connection-level
        # 印原文：只印 class name 會把憑證／DNS／逾時壓成同一個「URLError」，無從歸因
        return 3, [f"{url}\tERR\t\t{type(exc).__name__}: {str(exc)[:300]}"]
    title = ""
    body_lines: list[str] = []
    for line in text.splitlines():
        s = line.strip()
        if not body_lines and s.startswith("Title:"):
            title = s[len("Title:"):].strip()
            continue
        if not body_lines and (not s or s.startswith(_HEADER_PREFIXES)):
            continue
        body_lines.append(line)
    full_body = " ".join(body_lines).replace("\r", " ").replace("\t", " ").strip()
    body = full_body[:MAX_CHARS]
    truncated = len(full_body) > MAX_CHARS
    reason = block_reason(status, body)
    if reason:
        return 5, [f"{url}\tBLOCKED:{reason}\t{title}\t{body[:200]}"]
    if not body:
        return 2, [f"{url}\tEMPTY\t{title}\t"]
    status_str = f"{status}:TRUNCATED" if truncated else str(status)
    if save_dir is not None:
        os.makedirs(save_dir, exist_ok=True)
        url_hash = hashlib.sha1(url.encode("utf-8")).hexdigest()[:10]
        path = os.path.join(save_dir, f"{seq}-{url_hash}.txt")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(full_body)
        out.append(f"{url}\t{status_str}\t{title}\t{path}\t{len(full_body)}")
    else:
        out.append(f"{url}\t{status_str}\t{title}\t{body}")
    if grep is not None:
        for m in list(grep.finditer(full_body))[:20]:
            ctx = full_body[max(0, m.start() - 80):m.end() + 80]
            out.append("\tGREP\t" + ctx.replace("\n", " ").replace("\t", " "))
    return 0, out


def main(argv: list[str]) -> int:
    args = list(argv)
    if not args or args[0] == "help" or {"-h", "--help"} & set(args):
        print(__doc__.strip())
        return 0
    unknown = [a for a in args if a.startswith("-") and a not in ("--cell", "--max", "--save-dir", "--grep", "--no-budget", "--read")]
    if unknown:
        print(f"usage: unknown flag {unknown[0]}", file=sys.stderr)
        print(__doc__.strip(), file=sys.stderr)
        return 2
    cell = "global"
    max_hits = 5
    save_dir = None
    if "--cell" in args:
        i = args.index("--cell")
        if i + 1 >= len(args):
            print("usage: --cell needs a value", file=sys.stderr)
            return 2
        cell = args[i + 1]
        del args[i:i + 2]
    if "--max" in args:
        i = args.index("--max")
        if i + 1 >= len(args):
            print("usage: --max needs a value", file=sys.stderr)
            return 2
        max_hits = max(1, int(args[i + 1]))
        del args[i:i + 2]
    read_n = 0
    if "--read" in args:
        i = args.index("--read")
        if i + 1 >= len(args):
            print("usage: --read needs a value", file=sys.stderr)
            return 2
        try:
            read_n = int(args[i + 1])
        except ValueError:
            read_n = -1
        if read_n < 1:
            print("usage: --read needs a positive integer", file=sys.stderr)
            return 2
        del args[i:i + 2]
    if "--save-dir" in args:
        i = args.index("--save-dir")
        if i + 1 >= len(args):
            print("usage: --save-dir needs a value", file=sys.stderr)
            return 2
        save_dir = args[i + 1]
        del args[i:i + 2]
    grep = None
    if "--grep" in args:
        i = args.index("--grep")
        if i + 1 >= len(args):
            print("usage: --grep needs a value", file=sys.stderr)
            return 2
        try:
            grep = re.compile(args[i + 1], re.IGNORECASE)
        except re.error:
            print("usage: --grep: invalid regex", file=sys.stderr)
            return 2
        del args[i:i + 2]
    no_budget = "--no-budget" in args
    if no_budget:
        args.remove("--no-budget")
    if len(args) < 2 or args[0] not in ("search", "read"):
        print(__doc__.strip(), file=sys.stderr)
        return 2
    if args[0] == "search":
        rc, urls = search(" ".join(args[1:]), cell, max_hits)
        if rc == 0 and read_n:
            rc = max(rc, read_many(urls[:read_n], cell, save_dir=save_dir, grep=grep, budget=not no_budget))
        return rc
    urls: list[str] = []
    for arg in args[1:]:
        if arg.startswith("@"):
            with open(arg[1:], encoding="utf-8") as fh:
                for line in fh:
                    s = line.strip()
                    if s and not s.startswith("#"):
                        urls.append(s)
        else:
            urls.append(arg)
    return read_many(urls, cell, save_dir=save_dir, grep=grep, budget=not no_budget)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
