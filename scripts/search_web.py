#!/usr/bin/env python3
"""Search engines with an ordered fallback chain.

Usage:
    python3 search_web.py "<query>" [--engine auto|firecrawl|tavily|brave|serper|exa|ddg|ddg-lite|mojeek] [--max 10]

Output:
    One result per line:  TITLE<TAB>URL
    Organic results only; engine redirect wrappers (e.g. DDG uddg=) are unwrapped.

Exit codes:
    0  results found
    2  every engine blocked/failed
    3  engines answered but no organic results

Key discipline:
    Keys are read from ~/.config/vera-research/.env (KEY=VALUE lines only, never sourced).
    Engines without a key are silently skipped. Free engines always available.
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

try:
    from bs4 import BeautifulSoup  # type: ignore
except ImportError:
    BeautifulSoup = None

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:128.0) "
    "Gecko/20100101 Firefox/128.0"
)
HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
    "Accept-Encoding": "identity",
}

BLOCK_MARKERS = (
    "recaptcha",
    "cf-challenge",
    "cf_chl",
    "unusual traffic",
    "verify you are human",
    "are you human",
    "enable javascript and cookies",
    "please turn javascript on",
)
SHELL_TITLE = re.compile(r"just a moment", re.IGNORECASE)

ENV_FILE = Path(os.environ.get("VERA_ENV_FILE") or Path.home() / ".config" / "vera-research" / ".env")
COOLDOWN_FILE = Path(os.environ.get("TMPDIR", "/tmp")) / "err-fetch-cooldown.json"
COOLDOWN_SECONDS = 10 * 60
REQUEST_GAP_SECONDS = 3.0
REQUEST_TIMEOUT = 20

# engine -> candidate env key names (first present wins)
KEY_ENGINES: dict[str, list[str]] = {
    "firecrawl": ["FIRECRAWL_API_KEY"],
    "tavily": ["TAVILY_API_KEY"],
    "brave": ["BRAVE_SEARCH_API_KEY", "BRAVE_API_KEY"],
    "serper": ["SERPER_API_KEY"],
    "exa": ["EXA_API_KEY"],
}
FREE_ENGINES = ["ddg", "ddg-lite", "mojeek"]


def load_keys() -> dict[str, str]:
    keys: dict[str, str] = {}
    for k, v in os.environ.items():
        if k in ("FIRECRAWL_API_KEY", "TAVILY_API_KEY", "BRAVE_SEARCH_API_KEY",
                 "BRAVE_API_KEY", "SERPER_API_KEY", "EXA_API_KEY"):
            keys[k] = v.strip()
    if not ENV_FILE.exists():
        return keys
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip().strip("'\"")
        if k and k not in keys:
            keys[k] = v
    return keys


class Cooldown:
    def __init__(self) -> None:
        self._data: dict[str, dict] = {}
        if COOLDOWN_FILE.exists():
            try:
                self._data = json.loads(COOLDOWN_FILE.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                self._data = {}
        if not isinstance(self._data, dict):
            self._data = {}

    def blocked(self, key: str) -> bool:
        rec = self._data.get(key)
        return bool(rec) and rec.get("until", 0) > time.time()

    def hit(self, key: str, blocks: int = 1) -> None:
        now = time.time()
        rec = self._data.get(key, {})
        count = int(rec.get("count", 0)) + blocks
        until = now + COOLDOWN_SECONDS * min(count, 6)
        self._data[key] = {"count": count, "until": until}
        try:
            COOLDOWN_FILE.write_text(json.dumps(self._data, ensure_ascii=False))
        except OSError:
            pass


_cooldown = Cooldown()
_last_request: dict[str, float] = {}


def _respect_rate_limit(domain: str) -> None:
    gap = time.time() - _last_request.get(domain, 0)
    if gap < REQUEST_GAP_SECONDS:
        time.sleep(REQUEST_GAP_SECONDS - gap)
    _last_request[domain] = time.time()


def _is_blocked(body: str) -> bool:
    low = body.lower()
    for marker in BLOCK_MARKERS:
        if marker in low:
            return True
    return bool(SHELL_TITLE.search(low))


def _get(url: str, headers: dict | None = None) -> tuple[int, str]:
    req = urllib.request.Request(url, headers=headers or HEADERS)
    with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
        return resp.status, resp.read().decode("utf-8", errors="replace")


def _post(url: str, payload: dict, headers: dict | None = None) -> tuple[int, str]:
    data = json.dumps(payload).encode("utf-8")
    hdrs = dict(HEADERS)
    hdrs.setdefault("Content-Type", "application/json")
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(url, data=data, headers=hdrs, method="POST")
    with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
        return resp.status, resp.read().decode("utf-8", errors="replace")


def _unwrap_redirect(url: str) -> str:
    if "uddg=" not in url and "uddg=" not in urllib.parse.unquote(url):
        return url
    q = urllib.parse.urlparse(url)
    target = urllib.parse.parse_qs(q.query).get("uddg", [""])[0]
    return urllib.parse.unquote(target) if target else url


def _clean_title(text: str) -> str:
    if BeautifulSoup:
        text = BeautifulSoup(text, "html.parser").get_text(" ")
    else:
        text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _organic(results: list[tuple[str, str]]) -> list[tuple[str, str]]:
    seen: set[str] = set()
    out: list[tuple[str, str]] = []
    for title, url in results:
        url = _unwrap_redirect(url.strip()).strip()
        if not url:
            continue
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in ("http", "https"):
            continue
        if url in seen:
            continue
        seen.add(url)
        out.append((_clean_title(title), url))
    return out


def _engine_firecrawl(q: str, maxr: int, key: str) -> tuple[bool, list[tuple[str, str]]]:
    _respect_rate_limit("api.firecrawl.dev")
    status, body = _post(
        "https://api.firecrawl.dev/v1/search",
        {"query": q, "limit": maxr},
        {"Authorization": f"Bearer {key}"},
    )
    if status != 200:
        return False, []
    try:
        data = json.loads(body).get("data", [])
    except json.JSONDecodeError:
        return False, []
    return True, [(r.get("title", ""), r.get("url", "")) for r in data if r.get("url")]


def _engine_tavily(q: str, maxr: int, key: str) -> tuple[bool, list[tuple[str, str]]]:
    _respect_rate_limit("api.tavily.com")
    status, body = _post(
        "https://api.tavily.com/search",
        {"api_key": key, "query": q, "max_results": maxr, "search_depth": "basic"},
    )
    if status != 200:
        return False, []
    try:
        results = json.loads(body).get("results", [])
    except json.JSONDecodeError:
        return False, []
    return True, [(r.get("title", ""), r.get("url", "")) for r in results if r.get("url")]


def _engine_brave(q: str, maxr: int, key: str) -> tuple[bool, list[tuple[str, str]]]:
    _respect_rate_limit("api.search.brave.com")
    url = f"https://api.search.brave.com/res/v1/web/search?q={urllib.parse.quote(q)}&count={maxr}"
    try:
        # Brave API rejects the shared browser Accept header with HTTP 422; it needs JSON.
        status, body = _get(url, {**HEADERS, "Accept": "application/json", "X-Subscription-Token": key})
    except Exception:
        return False, []
    if status != 200:
        return False, []
    try:
        results = json.loads(body).get("web", {}).get("results", [])
    except json.JSONDecodeError:
        return False, []
    return True, [(r.get("title", ""), r.get("url", "")) for r in results if r.get("url")]


def _engine_serper(q: str, maxr: int, key: str) -> tuple[bool, list[tuple[str, str]]]:
    _respect_rate_limit("google.serper.dev")
    status, body = _post(
        "https://google.serper.dev/search",
        {"q": q, "num": maxr},
        {"X-API-KEY": key},
    )
    if status != 200:
        return False, []
    try:
        organic = json.loads(body).get("organic", [])
    except json.JSONDecodeError:
        return False, []
    return True, [(r.get("title", ""), r.get("link", "")) for r in organic if r.get("link")]


def _engine_exa(q: str, maxr: int, key: str) -> tuple[bool, list[tuple[str, str]]]:
    _respect_rate_limit("api.exa.ai")
    status, body = _post(
        "https://api.exa.ai/search",
        {"query": q, "numResults": maxr, "contents": {"text": False}},
        {"x-api-key": key},
    )
    if status != 200:
        return False, []
    try:
        results = json.loads(body).get("results", [])
    except json.JSONDecodeError:
        return False, []
    return True, [(r.get("title", ""), r.get("url", "")) for r in results if r.get("url")]


def _anchors(body: str, pattern: re.Pattern) -> list[tuple[str, str]]:
    out = []
    for m in pattern.finditer(body):
        href = html.unescape(m.group(1))
        title = _clean_title(m.group(2))
        out.append((title, href))
    return out


def _engine_ddg(q: str, maxr: int, lite: bool) -> tuple[bool, list[tuple[str, str]]]:
    host = "lite.duckduckgo.com" if lite else "html.duckduckgo.com"
    url = f"https://{host}/lite/?q={urllib.parse.quote(q)}" if lite else (
        f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(q)}"
    )
    _respect_rate_limit(host)
    try:
        status, body = _get(url)
    except Exception:
        return False, []
    if status == 403 or status == 429 or status == 503:
        return False, []
    if _is_blocked(body):
        return False, []
    if BeautifulSoup:
        soup = BeautifulSoup(body, "html.parser")
        anchors = []
        for a in soup.select("a.result__a") if not lite else soup.select("a"):
            href = a.get("href", "")
            if lite and href and not href.startswith(("http", "//duckduckgo.com/l")):
                continue
            anchors.append((a.get_text(" ", strip=True), href))
        results = anchors
    else:
        if lite:
            results = _anchors(body, re.compile(r'<a[^>]+rel="nofollow"[^>]+href="([^"]+)"[^>]*>(.*?)</a>', re.S))
        else:
            results = _anchors(body, re.compile(r'<a[^>]+class="[^"]*result__a[^"]*"[^>]+href="([^"]+)"[^>]*>(.*?)</a>', re.S))
    return True, results[:maxr]


def _engine_mojeek(q: str, maxr: int) -> tuple[bool, list[tuple[str, str]]]:
    url = f"https://www.mojeek.com/search?q={urllib.parse.quote(q)}"
    _respect_rate_limit("www.mojeek.com")
    try:
        status, body = _get(url)
    except Exception:
        return False, []
    if status == 403 or status == 429 or status == 503:
        return False, []
    if _is_blocked(body):
        return False, []
    if BeautifulSoup:
        soup = BeautifulSoup(body, "html.parser")
        results = [
            (a.get_text(" ", strip=True), a.get("href", ""))
            for a in soup.select("ul.results-standard a.title, ul.results-standard a")
            if a.get("href", "").startswith("http")
        ]
    else:
        results = _anchors(
            body,
            re.compile(r'<a[^>]+href="(https?://[^"]+)"[^>]*class="[^"]*title[^"]*"[^>]*>(.*?)</a>', re.S),
        )
    return True, results[:maxr]


def _engine_key(name: str, keys: dict[str, str]) -> str | None:
    for cand in KEY_ENGINES[name]:
        if cand in keys:
            return keys[cand]
    return None


def run_engine(name: str, q: str, maxr: int, keys: dict[str, str]) -> tuple[int, list[tuple[str, str]]]:
    """Return (status, results). status: 0=ok, 1=blocked/failed, 2=cooldown-skipped."""
    domain_map = {
        "firecrawl": "firecrawl",
        "tavily": "tavily",
        "brave": "brave",
        "serper": "serper",
        "exa": "exa",
        "ddg": "duckduckgo",
        "ddg-lite": "duckduckgo-lite",
        "mojeek": "mojeek",
    }
    ck = domain_map[name]
    if _cooldown.blocked(ck):
        print(f"[search] {name}: in cooldown, skip", file=sys.stderr)
        return 2, []

    ok, results = False, []
    if name == "firecrawl":
        ok, results = _engine_firecrawl(q, maxr, _engine_key("firecrawl", keys))
    elif name == "tavily":
        ok, results = _engine_tavily(q, maxr, _engine_key("tavily", keys))
    elif name == "brave":
        ok, results = _engine_brave(q, maxr, _engine_key("brave", keys))
    elif name == "serper":
        ok, results = _engine_serper(q, maxr, _engine_key("serper", keys))
    elif name == "exa":
        ok, results = _engine_exa(q, maxr, _engine_key("exa", keys))
    elif name == "ddg":
        ok, results = _engine_ddg(q, maxr, lite=False)
    elif name == "ddg-lite":
        ok, results = _engine_ddg(q, maxr, lite=True)
    elif name == "mojeek":
        ok, results = _engine_mojeek(q, maxr)

    if not ok:
        _cooldown.hit(ck)
        print(f"[search] {name}: blocked/failed, cooldown {COOLDOWN_SECONDS}s", file=sys.stderr)
        return 1, []
    results = _organic(results)[:maxr]
    if not results:
        print(f"[search] {name}: no organic results", file=sys.stderr)
        return 0, []
    return 0, results


def main() -> int:
    ap = argparse.ArgumentParser(description="Search engines with fallback chain.")
    ap.add_argument("query", help="search query")
    ap.add_argument(
        "--engine",
        choices=["auto", "firecrawl", "tavily", "brave", "serper", "exa", "ddg", "ddg-lite", "mojeek"],
        default="auto",
    )
    ap.add_argument("--max", type=int, default=10, help="max results (default 10)")
    args = ap.parse_args()

    keys = load_keys()
    if args.engine == "auto":
        order: list[str] = []
        for name, names in KEY_ENGINES.items():
            if any(k in keys for k in names):
                order.append(name)
        order += FREE_ENGINES
    elif args.engine in KEY_ENGINES:
        if not any(k in keys for k in KEY_ENGINES[args.engine]):
            print(f"[search] engine {args.engine}: no API key in ~/.config/vera-research/.env", file=sys.stderr)
            return 2
        order = [args.engine]
    else:
        order = [args.engine]

    any_blocked = False
    for name in order:
        status, results = run_engine(name, args.query, args.max, keys)
        if status == 2:
            continue
        if status == 1:
            any_blocked = True
            continue
        if results:
            for title, url in results:
                print(f"{title}\t{url}")
            return 0
    if any_blocked:
        return 2
    return 3


if __name__ == "__main__":
    sys.exit(main())
