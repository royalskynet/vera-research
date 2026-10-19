#!/usr/bin/env python3
"""Validate deterministic citation and release gates for a Markdown report."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

REFERENCE_HEADING = re.compile(
    r"^(?:#{1,6}\s*)?(?:[一二三四五六七八九十]+[、.]\s*)?"
    r"(?:参考资料|參考資料|参考来源(?:清单)?|參考來源(?:清單)?|References)\s*$",
    re.IGNORECASE,
)
CITATION = re.compile(r"\[(\d+)\]")
TABLE_REFERENCE = re.compile(r"^\|\s*(\d+)\s*\|")
LIST_REFERENCE = re.compile(r"^\s*\[(\d+)\]\s+")
URL = re.compile(r"https?://[^\s|)>]+", re.IGNORECASE)
CJK = re.compile(r"[\u4e00-\u9fff]")
# 常見「繁體專用」字（其簡體寫法不同）。正文命中比例過高＝誤用繁體（報告規定簡體中文）。
TRAD_ONLY = set("個們這時來對為與說報調資機關會國業經發電體學產實現際應點統認證無選進過還樣種將間開見聽圖書長員動務門問題響廠盡職風險審檢測數據網絡驗幣賬戶額轉錄權層級較擴週歷訊給區與從麼讓萬價設變讀處總計劃態辦結構條議護裝類參幾義")  # 覆 removed: 覆盖 is Simplified, was a false positive
# 硬性：任何工作階段方括號標記不得留在定稿（鐵律 2、鐵律 3）
UNRESOLVED_MARKERS = (
    "[待补来源]",
    "[待補來源]",
    "[⚠️ 待补来源]",
    "[⚠️ 待補來源]",
    "[待核实]",
    "[待核實]",
    "[资料不足]",
    "[資料不足]",
)


def _split_report(text: str) -> tuple[str, str, int | None]:
    """Return (body, reference_lines, reference_index)."""
    lines = text.splitlines()
    index = next(
        (i for i, line in enumerate(lines) if REFERENCE_HEADING.match(line.strip())),
        None,
    )
    if index is None:
        return "\n".join(lines), "", None
    body = "\n".join(lines[:index])
    return body, "\n".join(lines[index + 1 :]), index


CONCLUSION_HEAD = re.compile(r"^(?:#+\s*)?(?:\d+(?:\.\d+)*\s*)?(?:\*\*)?主要[结結][论論]")
LIST_ITEM = re.compile(r"^\s*(?:[-*]|\d+\.)\s+")


def check_conclusions(text: str) -> tuple[list[str], list[str]]:
    """主要結論每條須以粗體直接答案開頭（先答「能／不能／有條件」再列證據）。

    只貼條文、不回答問題的結論就是讓報告失去價值的根因，所以這條是 error。
    """
    errors: list[str] = []
    warnings: list[str] = []
    lines = text.splitlines()
    start = next((i for i, ln in enumerate(lines) if CONCLUSION_HEAD.match(ln.strip())), None)
    if start is None:
        return errors, warnings
    items = []
    for ln in lines[start + 1:]:
        s = ln.strip()
        if s.startswith("#") or s == "---":
            break
        if LIST_ITEM.match(ln) and not ln.startswith((" ", "\t")):
            items.append(s)
    if not items:
        errors.append("主要结论 has no list items")
    for n, s in enumerate(items, 1):
        if not LIST_ITEM.sub("", s).startswith("**"):
            errors.append(f"主要结论 item {n} must open with a bold direct answer: {s[:40]}")
    if not re.search(r"一句[话話][结結][论論]", text):
        warnings.append("missing 一句话结论 line")
    return errors, warnings


DIM_HEAD = re.compile(r"^###\s+D(\d+)\b")
DIM_ROW = re.compile(r"^\|\s*D(\d+)\b")


def check_dim_order(text: str) -> list[str]:
    """维度小节与表格维度列须按 D 编号升序：按风险或权重重排会让读者对不上编号。"""
    errors: list[str] = []
    heads = [int(m.group(1)) for ln in text.splitlines() if (m := DIM_HEAD.match(ln))]
    if heads != sorted(heads):
        errors.append(f"dimension sections out of order: {' '.join(f'D{n}' for n in heads)} (use D1..D9)")
    table: list[int] = []
    for ln in text.splitlines() + [""]:
        if ln.startswith("|"):
            if m := DIM_ROW.match(ln):
                table.append(int(m.group(1)))
            continue
        if table != sorted(table):
            errors.append(f"dimension table rows out of order: {' '.join(f'D{n}' for n in table)} (use D1..D9)")
        table = []
    return errors


def analyze(
    text: str,
) -> tuple[list[str], list[str], set[int], dict[int, str], str]:
    """Deterministic structural checks.

    Returns (errors, warnings, cited_numbers, references, body).
    references maps number -> full reference line.
    """
    errors, warnings = check_conclusions(text)
    errors.extend(check_dim_order(text))

    for marker in UNRESOLVED_MARKERS:
        if marker in text:
            errors.append(f"unresolved marker remains: {marker}")

    body, reference_text, reference_index = _split_report(text)
    if reference_index is None:
        errors.append("missing reference section heading")
        return errors, warnings, set(), {}, body

    reference_lines = reference_text.splitlines()
    citations = {int(value) for value in CITATION.findall(body)}
    if not citations:
        errors.append("no numeric citations found in report body")

    references: dict[int, str] = {}
    for line in reference_lines:
        match = TABLE_REFERENCE.match(line) or LIST_REFERENCE.match(line)
        if not match:
            continue
        number = int(match.group(1))
        if number in references:
            errors.append(f"duplicate reference number: {number}")
            continue
        references[number] = line
        if not URL.search(line):
            errors.append(f"reference {number} must contain an http(s) URL")

    for number in sorted(citations - references.keys()):
        errors.append(f"missing reference for citation [{number}]")

    if citations:
        expected = set(range(1, max(citations) + 1))
        for number in sorted(expected - citations):
            errors.append(f"citation numbering gap at [{number}]")

    for number in sorted(references.keys() - citations):
        warnings.append(f"reference [{number}] is not cited in the report body")

    return errors, warnings, citations, references, body


LEAK_PATTERNS = [
    ("AWS access key id", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("GitHub token", re.compile(r"\bgh[opsu]_[A-Za-z0-9]{20,}")),
    ("OpenAI-style key", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}")),
    ("PEM private key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("JWT", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.")),
    ("local home path", re.compile(r"/Users/[^/\s`\)]+/")),
]


def check_leaks(text: str) -> list[str]:
    """Credentials and local filesystem paths must never reach a delivered report."""
    found: list[str] = []
    for lineno, line in enumerate(text.splitlines(), 1):
        for label, pattern in LEAK_PATTERNS:
            if pattern.search(line):
                found.append(f"line {lineno}: {label} in delivered report")
    return found


def validate(text: str) -> tuple[list[str], list[str]]:
    """Public validation entry point; returns (errors, warnings)."""
    errors, warnings, _, _, _ = analyze(text)
    return errors + check_leaks(text), warnings


def build_checklist(
    body: str, references: dict[int, str]
) -> list[tuple[int, str, str]]:
    """Machine-extracted claim -> source checklist for human semantic review.

    Each body line that carries at least one [N] citation becomes one row:
    (line_number, claim_text, "；"-joined "[N] <url>" sources).
    """
    rows: list[tuple[int, str, str]] = []
    for lineno, line in enumerate(body.splitlines(), 1):
        numbers = sorted({int(v) for v in CITATION.findall(line)})
        if not numbers:
            continue
        claim_text = line.strip()
        if not claim_text:
            continue
        sources = []
        for n in numbers:
            src = references.get(n)
            urls = URL.findall(src) if src else []
            if urls:
                sources.append(f"[{n}] {urls[0]}")
            else:
                sources.append(f"[{n}] (missing reference)")
        rows.append((lineno, claim_text, "；".join(sources)))
    return rows


def _collect_urls(references: dict[int, str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for line in references.values():
        for url in URL.findall(line):
            url = url.rstrip(",.;，。；、")
            if url not in seen:
                seen.add(url)
                out.append(url)
    return out


UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/140.0 Safari/537.36"
)
# 反爬狀態碼：非死鏈證據，須人工用 reach.py read 二次確認
BOT_BLOCK = {401, 403, 405, 406, 409, 429, 503}


def _probe(url: str, method: str, timeout: float, insecure: bool = False):
    import ssl
    import urllib.error
    import urllib.request

    from urllib.parse import urljoin

    ctx = ssl._create_unverified_context() if insecure else None
    # Python < 3.11 的 HTTPRedirectHandler 不跟 308，會被當 HTTPError；手動跟（上限 5 跳）
    for _ in range(5):
        req = urllib.request.Request(url, method=method, headers={"User-Agent": UA})
        try:
            with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
                return True, resp.status
        except urllib.error.HTTPError as exc:
            loc = exc.headers.get("Location") if exc.headers else None
            if exc.code in (301, 302, 303, 307, 308) and loc:
                url = urljoin(url, loc)
                continue
            return False, exc.code
        except Exception as exc:  # noqa: BLE001 - connection-level
            return None, type(exc).__name__ + ": " + str(exc)
    return None, "too many redirects"


def check_url(url: str, timeout: float = 8.0) -> tuple[bool | None, object]:
    """Probe a URL. Returns (ok, detail).

    ok: True=reachable, False=dead (4xx/5xx that is not a bot block),
        None=inconclusive (connection-level failure, or anti-bot status that
        needs a second pass with reach.py read before calling it dead).
    """
    ok, detail = _probe(url, "HEAD", timeout)
    # HEAD often blocked or unimplemented; retry GET before judging
    if ok is not True:
        ok2, detail2 = _probe(url, "GET", timeout)
        if ok2 is not None or ok is None:
            ok, detail = ok2, detail2
    # TLS chain rejected locally (e.g. missing Subject Key Identifier) != dead
    if ok is None and "CERTIFICATE_VERIFY_FAILED" in str(detail):
        ok3, detail3 = _probe(url, "GET", timeout, insecure=True)
        if ok3 is True:
            return True, f"{detail3} (TLS chain unverified locally)"
    if ok is False and detail in BOT_BLOCK:
        return None, f"HTTP {detail} anti-bot; confirm with reach.py read before calling it dead"
    return ok, detail


def check_urls(urls: list[str], timeout: float = 8.0) -> tuple[bool, list[tuple[str, bool | None, object]]]:
    """HEAD-check every URL. Returns (offline, [(url, ok, detail)]).

    offline=True when every request failed at connection level (likely no network).
    """
    from concurrent.futures import ThreadPoolExecutor
    from urllib.parse import urlsplit

    # 不同網域平行、同網域依序（避免對單站並發觸發反爬）；回傳維持輸入順序
    by_host: dict[str, list[int]] = {}
    for i, url in enumerate(urls):
        by_host.setdefault(urlsplit(url).netloc.lower(), []).append(i)
    res: list[tuple[bool | None, object]] = [(None, "")] * len(urls)

    def run_host(idx: list[int]) -> None:
        for i in idx:
            res[i] = check_url(urls[i], timeout=timeout)

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(run_host, by_host.values()))
    statuses = [(u, ok, detail) for u, (ok, detail) in zip(urls, res)]
    connection_fail = sum(1 for _, ok, _ in statuses if ok is None)
    offline = len(urls) > 0 and connection_fail == len(urls)
    return offline, statuses


def check_ledger(
    body: str, references: dict[int, str], ledger_path: Path
) -> tuple[list[str], bool]:
    """Deep-mode ledger cross-check.

    Loads a YAML sidecar (sources + claims). Verifies:
    - every claim entry that names a source_id resolves to a declared source;
    - citations actually present in the body are accounted for by a claim record.
    Returns (messages, fatal). Fatal=False means only advisory notes.
    """
    errors: list[str] = []
    try:
        import yaml

        data = yaml.safe_load(ledger_path.read_text(encoding="utf-8"))
    except ImportError:
        return ["WARN: pyyaml not installed; ledger cross-check skipped"], False
    except Exception as exc:  # noqa: BLE001 - malformed sidecar
        return [f"invalid ledger YAML: {exc}"], True

    if not isinstance(data, dict):
        return ["invalid ledger: expected a mapping with 'sources' and 'claims'"], True

    sources = data.get("sources") or []
    claims = data.get("claims") or []
    if not isinstance(sources, list) or not isinstance(claims, list):
        return ["invalid ledger: 'sources' and 'claims' must be lists"], True

    source_ids = {
        s.get("id") for s in sources if isinstance(s, dict) and s.get("id")
    }
    body_cites = {int(v) for v in CITATION.findall(body)}

    ledger_refnums: set[int] = set()
    for c in claims:
        if not isinstance(c, dict):
            continue
        sid = c.get("source_id") or c.get("source")
        if sid and sid not in source_ids:
            errors.append(
                f"ledger claim '{c.get('id', '?')}' references unknown source '{sid}'"
            )
        ref = c.get("ref")
        if isinstance(ref, int):
            ledger_refnums.add(ref)
            if ref not in references:
                errors.append(
                    f"ledger claim '{c.get('id', '?')}' ref [{ref}] has no report reference"
                )

    # Every in-body citation should have a claim record in deep mode.
    uncovered = sorted(body_cites - ledger_refnums)
    if uncovered:
        errors.append(
            "ledger has no claim record for in-body citation(s) "
            + ", ".join(f"[{n}]" for n in uncovered)
        )

    if not errors:
        errors.append(f"ledger cross-check OK ({len(claims)} claims, {len(sources)} sources)")
    return errors, False


ANSWER_TYPES = {
    "能": "能", "是": "能",
    "不能": "不能", "否": "不能",
    "有条件": "有条件", "有條件": "有条件",
    "未能核实": "未能核实", "未能核實": "未能核实",
}
CORE_KEYS = {"核心", "core"}
ONE_LINE = re.compile(r"一句[话話][结結][论論]")
MIN_SNIPPET = 6


def _norm_text(s: str) -> str:
    return re.sub(r"\s+", "", s.replace("**", "").replace("`", ""))


def parse_answer_map(text: str) -> tuple[list[dict], list[str]]:
    """Read the answer map sidecar: | 格 | 题号 | 答案类型 | 报告原句 |.

    The sidecar lives in the work dir (audit/answer-map.md), never in the report:
    ledger ids are process terms the delivered report must not carry.
    """
    rows: list[dict] = []
    errors: list[str] = []
    for lineno, line in enumerate(text.splitlines(), 1):
        s = line.strip()
        if not s.startswith("|"):
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if len(cells) < 4:
            errors.append(f"answer map line {lineno}: expected 4 columns (格|题号|答案类型|报告原句)")
            continue
        cell, qid, kind, snippet = cells[0], cells[1], cells[2], "|".join(cells[3:]).strip()
        if set(cell) <= set("-: ") or cell in ("格", "cell"):
            continue  # separator / header
        rows.append({"line": lineno, "cell": cell, "qid": qid, "kind": kind, "snippet": snippet})
    return rows, errors


def check_answer_map(report: str, ledger: dict, map_text: str) -> tuple[list[str], list[str]]:
    """Cross-check ledger questions -> answer map -> delivered report.

    Catches what neither gate catches alone: a question closed in the ledger whose answer
    was cut or blurred while drafting, an evidence-less question dressed as a firm answer,
    and a one-line conclusion that does not address the registered core question.
    Proves an answer is present, not that it is right; semantics stay with round 3.
    """
    rows, errors = parse_answer_map(map_text)
    warnings: list[str] = []
    norm_report = _norm_text(report)
    one_line = next((ln for ln in report.splitlines() if ONE_LINE.search(ln)), "")

    questions: dict[tuple[str, str], dict] = {}
    for cname, cd in (ledger.get("cells") or {}).items():
        for q in cd.get("questions", []) or []:
            questions[(cname, q["id"])] = q

    seen: set[tuple[str, str]] = set()
    core_rows = []
    for r in rows:
        tag = f"answer map line {r['line']}"
        kind = ANSWER_TYPES.get(r["kind"])
        if kind is None:
            errors.append(f"{tag}: 答案类型 '{r['kind']}' not in 能/不能/有条件/未能核实")
        snip = _norm_text(r["snippet"])
        if len(snip) < MIN_SNIPPET:
            errors.append(f"{tag}: 报告原句 too short (<{MIN_SNIPPET} chars) to locate")
        elif snip not in norm_report:
            errors.append(f"{tag}: 报告原句 not found verbatim in report: {r['snippet'][:40]}")
        if r["cell"].lower() in CORE_KEYS:
            core_rows.append(r)
            if snip and snip not in _norm_text(one_line):
                errors.append(f"{tag}: core answer must sit on the 一句话结论 line")
            continue
        key = (r["cell"], r["qid"])
        q = questions.get(key)
        if q is None:
            errors.append(f"{tag}: unknown ledger question {r['cell']} {r['qid']}")
            continue
        if key in seen:
            errors.append(f"{tag}: duplicate row for {r['cell']} {r['qid']}")
        seen.add(key)
        if q.get("state") == "none" and kind and kind != "未能核实":
            errors.append(f"{tag}: {r['cell']} {r['qid']} closed with --none in ledger "
                          f"but mapped as '{kind}' (no source can back a firm answer)")
        elif q.get("state") == "answered" and kind == "未能核实":
            warnings.append(f"{tag}: {r['cell']} {r['qid']} had sources in ledger but maps to 未能核实")

    for key, q in questions.items():
        if q.get("state") == "open":
            errors.append(f"ledger question {key[0]} {key[1]} still open: {q['q'][:40]}")
        elif key not in seen:
            errors.append(f"ledger question {key[0]} {key[1]} not mapped to the report: {q['q'][:40]}")

    core = ledger.get("core_question")
    if core:
        if not core_rows:
            errors.append(f"no 核心 row answering the core question: {core[:40]}")
        elif len(core_rows) > 1:
            errors.append("more than one 核心 row")
        if not one_line:
            errors.append("core question registered but report has no 一句话结论 line")
    elif ledger.get("require_questions"):
        errors.append("ledger has no core question; run budget.py core \"<核心决策问题>\"")
    else:
        warnings.append("legacy ledger without core question; core check skipped")
    return errors, warnings


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Check Markdown citation numbering, reference URLs, and unresolved markers; "
            "optionally emit a claim->source checklist, probe URL liveness, and "
            "cross-check a deep-mode YAML ledger."
        )
    )
    parser.add_argument("report", type=Path, help="Markdown report to validate")
    parser.add_argument(
        "--check-list",
        action="store_true",
        help="print machine-extracted claim -> source checklist for human semantic review",
    )
    parser.add_argument(
        "--check-urls",
        action="store_true",
        help="HEAD-probe reference URLs for liveness (skipped if offline)",
    )
    parser.add_argument("--lang", choices=("zh-hans", "any"), default="any",
                        help="zh-hans: fail when the body looks like Traditional Chinese (report language rule)")
    parser.add_argument(
        "--ledger",
        type=Path,
        metavar="LEDGER.yaml",
        help="deep-mode YAML ledger sidecar path to cross-check",
    )
    parser.add_argument(
        "--answer-map",
        type=Path,
        metavar="ANSWER-MAP.md",
        help="ledger question -> report sentence map (work dir sidecar); requires --budget",
    )
    parser.add_argument(
        "--budget",
        type=Path,
        metavar="LEDGER.json",
        help="budget.py ledger (.research-budget.json) holding registered questions and core question",
    )
    args = parser.parse_args()
    if bool(args.answer_map) != bool(args.budget):
        print("FAIL: --answer-map and --budget must be given together")
        return 2

    try:
        text = args.report.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"FAIL: cannot read {args.report}: {exc}")
        return 2

    errors, warnings, citations, references, body = analyze(text)

    if args.lang == "zh-hans":
        cjk_total = len(CJK.findall(body))
        trad = sum(1 for ch in body if ch in TRAD_ONLY)
        sample = "".join(sorted({ch for ch in body if ch in TRAD_ONLY})[:30])
        if cjk_total and trad >= 20 and trad / cjk_total >= 0.01:
            errors.append(f"body looks like Traditional Chinese ({trad} traditional-only chars of {cjk_total} CJK: {sample}); report must be Simplified Chinese")
        elif trad:
            # below threshold: usually stray chars from a Traditional-Chinese draft; proper nouns are the only legit case
            warnings.append(f"{trad} traditional-only chars below threshold ({sample}); convert unless they are proper nouns")

    for warning in warnings:
        print(f"WARN: {warning}")

    if args.check_list:
        rows = build_checklist(body, references)
        print("\n== claim -> source checklist (human semantic review) ==")
        if rows:
            for lineno, claim_text, sources in rows:
                print(f"  L{lineno} | {claim_text}  ->  {sources}")
        else:
            print("  (no claim-carrying lines extracted)")
        print("  -- review each row: does the cited source semantically support the claim?")

    if args.check_urls:
        urls = _collect_urls(references)
        offline, statuses = check_urls(urls)
        if offline:
            print("\nURL liveness check skipped (no network / connection-level failures on all URLs)")
        else:
            dead = 0
            print("\n== reference URL liveness ==")
            for url, ok, detail in statuses:
                if ok is True:
                    print(f"  OK   {url}  ({detail})")
                elif ok is False:
                    dead += 1
                    print(f"  DEAD {url}  (HTTP {detail})")
                    errors.append(f"dead reference URL: {url} (HTTP {detail})")
                else:
                    print(f"  ?    {url}  ({detail})")
            if dead:
                print(f"  -> {dead} dead reference URL(s)")

    leaks = check_leaks(text)
    if leaks:
        print("\n== credential / local-path leak scan ==")
        for msg in leaks:
            print("FAIL: " + msg)
        errors.extend(leaks)

    if args.ledger:
        lerrors, _ = check_ledger(body, references, args.ledger)
        ledger_errs = [
            m for m in lerrors
            if "cross-check OK" not in m and "skipped" not in m
        ]
        print("\n== deep-mode ledger cross-check ==")
        for msg in lerrors:
            prefix = "FAIL: " if msg in ledger_errs else "  "
            print(prefix + msg)
        errors.extend(ledger_errs)

    if args.answer_map:
        import json

        print("\n== answer coverage (ledger -> answer map -> report) ==")
        try:
            ledger = json.loads(args.budget.read_text(encoding="utf-8"))
            map_text = args.answer_map.read_text(encoding="utf-8")
        except (OSError, ValueError) as exc:
            print(f"FAIL: cannot read answer map or ledger: {exc}")
            return 2
        aerrors, awarnings = check_answer_map(text, ledger, map_text)
        for w in awarnings:
            print(f"WARN: {w}")
        n_q = sum(len(cd.get("questions", []) or []) for cd in (ledger.get("cells") or {}).values())
        if not aerrors:
            print(f"  {n_q} ledger question(s) + core question mapped to report sentences")
        errors.extend(aerrors)

    if errors:
        for error in errors:
            print(f"FAIL: {error}")
        return 1

    citation_count = len({int(value) for value in CITATION.findall(body)})
    print(f"PASS: {citation_count} cited source(s); deterministic checks complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
