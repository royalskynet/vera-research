#!/usr/bin/env python3
"""Turn draft citation tags into sequential [N] and emit the source table.

Why: when collection is split across deep workers (one ledger per dimension), the draft
cannot allocate [N] up front. Cite by tag, number once at finalize.

Draft convention
  tag        = <PREFIX>R<n>, e.g. [D1R2]; PREFIX = source-table file stem (D1..D9),
               `sources.md` (round 2) maps to X, e.g. [XR3]
  <<SOURCES>> = placeholder where the reference-list table goes
Source table rows (ledger format used by deep workers)
  | R<n> | 等級 | 標題 | URL | 查閱日期 | 頁面日期 | 摘錄 | 支持題號 |

Usage
  number_cites.py work/draft.md --sources work/round1/D*.md work/round2/sources.md > report.md

Numbers follow first appearance; the same URL cited under two tags gets one number;
adjacent duplicates [3][3] collapse. Unknown tag -> stderr `MISSING <tag>`, exit 1
(still numbered so the draft stays readable; fix before finalizing).
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

TAG_RE = re.compile(r"\[([A-Z]\d*R\d+)\]")
ROW_RE = re.compile(r"^\|\s*(R\d+)\s*\|")


def load_sources(paths: list[Path]) -> dict[str, tuple[str, str, str, str, str]]:
    src: dict[str, tuple[str, str, str, str, str]] = {}
    for p in paths:
        prefix = "X" if p.stem == "sources" else p.stem.upper()
        for line in p.read_text(encoding="utf-8").splitlines():
            m = ROW_RE.match(line)
            if not m:
                continue
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) < 6:
                continue
            rid, grade, title, url, date, pdate = cells[:6]
            src[f"{prefix}{rid}"] = (title, grade, url, date, pdate)
    return src


def number(text: str, src: dict[str, tuple[str, str, str, str, str]]) -> tuple[str, list[str], list[str]]:
    order: list[str] = []
    num: dict[str, int] = {}
    by_url: dict[str, str] = {}
    missing: list[str] = []
    for m in TAG_RE.finditer(text):
        t = m.group(1)
        if t in num:
            continue
        if t not in src:
            missing.append(t)
            num[t] = len(order) + 1
            order.append(t)
            continue
        url = src[t][2].rstrip("/")
        if url in by_url:
            num[t] = num[by_url[url]]
            continue
        by_url[url] = t
        num[t] = len(order) + 1
        order.append(t)

    body = TAG_RE.sub(lambda m: f"[{num[m.group(1)]}]", text)
    body = re.sub(r"(\[(\d+)\])(\[\2\])+", r"\1", body)

    rows = ["| 序号 | 来源标题 | 类型 | 链接 | 查阅日期 | 页面日期 |", "|---|---|---|---|---|---|"]
    for i, t in enumerate(order, 1):
        title, grade, url, date, pdate = src.get(t, (t, "?", "", "", ""))
        rows.append(f"| {i} | {title} | {grade} | {url} | {date} | {pdate} |")
    body = body.replace("<<SOURCES>>", "\n".join(rows))
    return body, order, missing


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("draft", type=Path)
    ap.add_argument("--sources", nargs="+", type=Path, required=True, help="source-table markdown files")
    args = ap.parse_args()
    body, order, missing = number(args.draft.read_text(encoding="utf-8"), load_sources(args.sources))
    sys.stdout.write(body)
    for t in missing:
        print(f"MISSING {t}", file=sys.stderr)
    print(f"tags={len(order)} missing={len(missing)}", file=sys.stderr)
    return 1 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
