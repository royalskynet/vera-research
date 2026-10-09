#!/usr/bin/env python3
"""Research budget & stop-rule ledger (stdlib only). Mechanical gate, not advisory.

Coverage matrix = platforms x dimensions. Each cell starts OPEN; FILLED (>=1 verified
source with [N]) or CLOSED (budget exhausted with no source). Round 1 ends when no
cell is OPEN. Hard counters, not model judgment.

CLI (each prints one line to stdout, fixed exit code):
    budget.py init --platforms A,B --dims x,y [--fetch-per-cell 3] [--search-per-cell 2]
                   [--mode competitor|vendor-dd|academic] [--max-gaps 10] [--minutes 90]
    budget.py spend fetch|search <cell> [--q "<查詢詞>"] [--channel reach|camofox]
    budget.py trail <cell> [--hits N] [--q "<查詢詞>"]
    budget.py nonew <cell>
    budget.py core "<核心決策問題>"                # 登記使用者指令要回答的那一題；新帳本 phase final 前必填
    budget.py ask <cell> "<問題>" ["<問題>" ...]  # 登記必答題；抓取額度＝max(每格預設, ceil(0.75×題數))
    budget.py answer <cell> <Q#> <N[,M]> | --none "<理由>" [--cand <URL>]
    budget.py fill <cell> [N] [--sole "<理由>"]   # FILLED 需 ≥min_refs 個不同 [N] 且登記題全結案，否則 PARTIAL
    budget.py close <cell> <reason...>
    budget.py entities <brand> <legal1[,legal2,...]> [--aliases a,b] [--former f] [--people p]
    budget.py gaps
    budget.py phase round2 --gaps A/x,B/y | draft|integrated|round3|final
    budget.py phase deep --gaps A/x,B/y [--fetch-per-gap 4] [--search-per-gap 2] [--deep-minutes 30]
    budget.py verify <cell> <url> --quote "<原文摘錄>"
    budget.py status
    budget.py --selftest

Exit codes: 0 = ok, 2 = usage/validation error, 4 = budget exhausted (EXHAUSTED/HALT).

Deep round (camofox): after the agent-reach rounds, gaps that remain can get ONE extra
camofox-only round. Its budget is separate (per-gap caps + own clock), never counted in
totals/total_*_cap. Every page it renders is saved as evidence; `fill` on a deep gap is
refused until `verify` has matched a verbatim quote against a saved, unblocked body.
Ledger path: $RESEARCH_BUDGET or ./.research-budget.json
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import fcntl
import tempfile
from contextlib import contextmanager
from math import ceil
from datetime import datetime, timezone
from pathlib import Path


def ledger_path() -> Path:
    return Path(os.environ.get("RESEARCH_BUDGET", "./.research-budget.json")).expanduser()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def load(path: Path) -> dict:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def save(path: Path, data: dict) -> None:
    # tmp + os.replace: a concurrent reader never sees a half-written ledger.
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent or ".")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except BaseException:
        os.unlink(tmp)
        raise


_lock_depth = 0


@contextmanager
def ledger_lock(path: Path):
    """Exclusive flock on a sibling `.lock` file around a whole load→modify→save,
    so parallel deep runs sharing one ledger serialise instead of losing spends.
    Reentrant within a process (camofox holds it, then _spend re-enters main_core)."""
    global _lock_depth
    if _lock_depth:
        _lock_depth += 1
        try:
            yield
        finally:
            _lock_depth -= 1
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path.with_name(path.name + ".lock"), "a") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        _lock_depth = 1
        try:
            yield
        finally:
            _lock_depth = 0
            fcntl.flock(fh, fcntl.LOCK_UN)


# 雙層上限（借鏡 open_deep_research：內層每研究單位 tool call 上限＋外層總量上限）。
# 舊版總量寫死 60/40、>24 格降到每格 2 抓 1 搜，與「每格 ≥2 來源、≥3 題」下限衝突，
# 實測 126 格中 36 格只抓 1 次就 FILLED（2026-10-05 審計）。防失控靠 nonew／重複查詢／牆鐘，不靠把額度壓到不夠用。
MODE_CEILINGS = {  # mode: (total_fetch_ceiling, total_search_ceiling)
    "competitor": (120, 80),
    "vendor-dd": (90, 60),
    "academic": (100, 60),
    "competitor-single": (60, 36),
}
BIG_MATRIX = 36  # 超過此格數每格降為 2 抓 2 搜（搜尋不再降到 1：1 次搜尋答不了 3 題）
MIN_REFS = 2  # 每格 FILLED 需 ≥2 個不同 [N]；唯一一手來源走 fill --sole "<理由>"
# 抓取額度依題數放大：cex-fraud-controls（2026-10-07 量測）每格約 6 題只准抓 3 頁，
# 23/25 格額度用滿、約 30% 題目無實質答案，其中 19 條是「找到候選頁、額度用完沒抓」。
# 實測一頁常答到不只一題，故取 0.75 而非 1。ponytail: 固定比例，有多場答題數據再按模式校正。
Q_FETCH_RATIO = 0.75
MAX_Q_PER_CELL = 8  # references/deep-mode.md：每 WP 必答問題 3–8 題；擋灌題換額度


def q_fetch_extra(data: dict, cd: dict) -> int:
    return max(0, ceil(Q_FETCH_RATIO * len(cd.get("questions", []))) - data["fetch_per_cell"])


def cell_cap(data: dict, cd: dict, kind: str) -> int:
    """單格第一輪額度＝每格預設＋加碼（topup／自動借）＋題數放大（只放大抓取）。"""
    cap = data[f"{kind}_per_cell"] + cd.get(f"bonus_{kind}", 0)
    return cap + cd.get("q_fetch", 0) if kind == "fetch" else cap


def new_ledger(*, platforms, dims, fetch_pc, search_pc, max_gaps, minutes, mode="competitor"):
    cells = {}
    for p in platforms:
        for d in dims:
            cells[f"{p}/{d}"] = {
                "state": "OPEN", "fetch": 0, "search": 0, "no_new": 0,
                "bonus_fetch": 0, "bonus_search": 0,
                "refs": [], "r2_fetch": 0, "r2_search": 0,
            }
    n = len(platforms) * len(dims)
    if n > BIG_MATRIX:  # downgrade per-cell budget for big matrices
        fetch_pc = min(fetch_pc, 2)
        search_pc = min(search_pc, 2)
    fceil, sceil = MODE_CEILINGS.get(mode, MODE_CEILINGS["competitor"])
    fcap, scap = min(n * fetch_pc, fceil), min(n * search_pc, sceil)
    ledger = {
        "created": now_iso(),
        "minutes": minutes,
        "fetch_per_cell": fetch_pc,
        "search_per_cell": search_pc,
        "max_gaps": max_gaps,
        "min_refs": MIN_REFS,
        "total_fetch_cap": fcap,
        "total_search_cap": scap,
        "reserve_fetch": ceil(0.15 * fcap),
        "reserve_search": ceil(0.15 * scap),
        "reserve_used_fetch": 0,
        "reserve_used_search": 0,
        "phase": "round1",
        "gaps": [],
        "cells": cells,
        "totals": {"fetch": 0, "search": 0},
        "entities": [],
        "require_questions": True,  # 舊帳本沒這欄＝不設閘
    }
    return ledger


def cell_ok(data: dict, cell: str) -> str | None:
    """Return reason string if spend on this cell is disallowed, else None."""
    # wall-clock HALT first
    phase = data["phase"]
    elapsed = int((now_utc() - datetime.fromisoformat(data["created"])).total_seconds() / 60)
    if phase != "deep" and elapsed >= data["minutes"]:
        return f"elapsed={elapsed}"
    if phase == "deep":
        d = data["deep"]
        dl = int((now_utc() - datetime.fromisoformat(d["started"])).total_seconds() / 60)
        return f"elapsed={dl}" if dl >= d["minutes"] else None
    cells = data["cells"]
    if phase == "round1":
        state = cells[cell]["state"]
        # FILLED＝來源下限已達，不是停止蒐集：格內額度沒用完仍可補答必答題。
        # 只擋 CLOSED；收斂靠每格額度、總上限、nonew 與牆鐘（fix 10039）。
        if state == "CLOSED":
            return f"state_{state}"
        # 主體解析閘門：D2（牌照名冊對照）與 D6（訴訟／制裁查詢）必須在
        # 「主體解析表」（entities）產出後才准花費——否則會拿品牌名去查名冊，
        # 查無即誤下「無牌／無負面」。這是機械前置依賴，不是提醒。
        dim = cell.split("/", 1)[-1]
        if dim in ("D2", "D6") and not data.get("entities"):
            return "no_entities"
        # 題目閘：必答題由 LLM 依使用者指令生成並 ask 登記，沒登記不准花第一筆。
        # 只寫在 SKILL.md 的「先列問題」符合率近 0，6.5.0 的 ask 不呼叫就退回舊語義。
        if data.get("require_questions") and not cells[cell].get("questions"):
            return "no_questions"
    return None


# 模式預設（SSOT：SKILL.md「調研預算與停損」）：search_per_cell, fetch_per_cell, max_gaps, minutes
MODE_PRESETS = {
    "competitor": (2, 3, 10, 120),
    "vendor-dd": (4, 6, 6, 150),
    "academic": (3, 4, 8, 120),
    # 單平台深度調研（competitor 子模式）：cells ≤ 12 時自動應用。單平台＝要深度，額度高於多平台
    "competitor-single": (3, 5, 6, 120),
}


def do_init(args, path):
    platforms = [s for s in args.platforms.split(",") if s]
    dims = [s for s in args.dims.split(",") if s]
    if not platforms or not dims:
        print("ERROR no platforms or dims")
        return 2
    mode = args.mode or "competitor"
    
    # 單平台深度調研自動降級：1 平台 × ≤12 維度 → competitor-single
    n_cells = len(platforms) * len(dims)
    if mode == "competitor" and len(platforms) == 1 and n_cells <= 12:
        mode = "competitor-single"
        print(f"[auto] 單平台 {n_cells} cells → 套用 competitor-single 模式")
    
    p_search, p_fetch, p_gaps, p_minutes = MODE_PRESETS[mode]
    fetch_pc = args.fetch_per_cell if args.fetch_per_cell is not None else p_fetch
    search_pc = args.search_per_cell if args.search_per_cell is not None else p_search
    max_gaps = args.max_gaps if args.max_gaps is not None else p_gaps
    minutes = args.minutes if args.minutes is not None else p_minutes
    led = new_ledger(
        platforms=platforms, dims=dims, fetch_pc=fetch_pc,
        search_pc=search_pc, max_gaps=max_gaps, minutes=minutes, mode=mode,
    )
    led["mode"] = mode
    save(path, led)
    n = len(platforms) * len(dims)
    print(f"INIT mode={mode} cells={n} fetch_per_cell={led['fetch_per_cell']} "
          f"search_per_cell={led['search_per_cell']} "
          f"total_fetch_cap={led['total_fetch_cap']} "
          f"total_search_cap={led['total_search_cap']} minutes={led['minutes']}")
    return 0


def do_spend(args, path):
    data = load(path)
    cell = args.cell
    cells = data["cells"]
    if cell not in cells:
        cells[cell] = {
            "state": "OPEN", "fetch": 0, "search": 0, "no_new": 0,
                "bonus_fetch": 0, "bonus_search": 0,
            "refs": [], "r2_fetch": 0, "r2_search": 0,
        }
        data.setdefault("gaps", [])
    kind = args.kind
    if kind == "search":
        q = getattr(args, "q", None)
        if q:
            norm = q.strip().lower()
            for rec in cells.get(cell, {}).get("queries", []):
                if rec.get("refunded"):
                    continue  # 工具掛掉退款的查詢不算用過，備援通道可重送
                if rec.get("q", "").strip().lower() == norm:
                    print(f"EXHAUSTED cell={cell} reason=duplicate_query")
                    return 4
    reason = cell_ok(data, cell)
    if reason is not None:
        if reason.startswith("elapsed"):
            print(f"HALT time {reason}")
        else:
            print(f"EXHAUSTED cell={cell} reason={reason}")
        return 4
    phase = data["phase"]
    channel = getattr(args, "channel", None) or "reach"
    if phase == "deep":
        return _spend_deep(data, path, cell, kind, channel, getattr(args, "q", None))
    if phase == "round2":
        if cell not in data["gaps"]:
            print(f"EXHAUSTED cell={cell} reason=not_a_gap")
            return 4
        # 第二輪兩通道各恰一次：camofox 另記 r2c_*，不與 agent-reach 搶同一格額度
        key = f"r2c_{kind}" if channel == "camofox" else f"r2_{kind}"
        cap = 1
        used = cells[cell].get(key, 0)
        if used >= cap:
            print(f"EXHAUSTED cell={cell} reason=cell_cap")
            return 4
        cells[cell][key] = used + 1
    else:
        key = kind
        cap = cell_cap(data, cells[cell], kind)
        if cells[cell][key] >= cap:
            # 自動向保留池借 1 單位：子代理從不手動 topup（實測保留池 0 次被用），
            # 只借給未 FILLED 的格（尾款優先補品質下限），每格每種限借 1 次；
            # 防失控仍靠 no_new×2 關格與牆鐘。ponytail: 先到先借，要公平再改按缺口排序
            cd = cells[cell]
            borrowed = cd.setdefault("borrowed", {})
            if (cd["state"] != "FILLED" and not borrowed.get(kind)
                    and data[f"reserve_used_{kind}"] < data[f"reserve_{kind}"]):
                borrowed[kind] = 1
                cd[f"bonus_{kind}"] = cd.get(f"bonus_{kind}", 0) + 1
                data[f"reserve_used_{kind}"] += 1
                data[f"total_{kind}_cap"] += 1
                print(f"BORROW cell={cell} kind={kind} reserve_left="
                      f"{data[f'reserve_{kind}'] - data[f'reserve_used_{kind}']}", file=sys.stderr)
            else:
                print(f"EXHAUSTED cell={cell} reason=cell_cap")
                return 4
        total_key = f"total_{kind}_cap"
        if data["totals"][kind] >= data[total_key]:
            print(f"EXHAUSTED cell={cell} reason=total_cap")
            return 4
        cells[cell][key] += 1
    if kind == "search":
        q = getattr(args, "q", None)
        if q:
            cells[cell].setdefault("queries", []).append(
                {"at": now_iso(), "q": q, "hits": None}
            )
    data["totals"][kind] += 1
    save(path, data)
    cap = cell_cap(data, cells[cell], kind) if phase != "round2" else 1
    rem_cell = max(cap - cells[cell][key], 0)
    rem_total = max(data[f"total_{kind}_cap"] - data["totals"][kind], 0) if phase != "round2" else 0
    print(f"OK kind={kind} cell={cell} remaining_cell={rem_cell} remaining_total={rem_total}")
    return 0


def _spend_deep(data, path, cell, kind, channel, q):
    """camofox 深入輪記帳：獨立額度，不動 totals／total_*_cap。"""
    d = data["deep"]
    if channel != "camofox":
        print(f"EXHAUSTED cell={cell} reason=deep_camofox_only")
        return 4
    if cell not in d["gaps"]:
        print(f"EXHAUSTED cell={cell} reason=not_a_gap")
        return 4
    used = d["used"].setdefault(cell, {"fetch": 0, "search": 0})
    cap = d[f"{kind}_per_gap"]
    if used[kind] >= cap:
        print(f"EXHAUSTED cell={cell} reason=deep_cap")
        return 4
    used[kind] += 1
    if kind == "search" and q:
        data["cells"][cell].setdefault("queries", []).append({"at": now_iso(), "q": q, "hits": None})
    save(path, data)
    print(f"OK kind={kind} cell={cell} deep remaining_cell={cap - used[kind]}")
    return 0


def evidence_dir() -> Path:
    return ledger_path().parent / ".research-deep"


def add_evidence(data: dict, cell: str, url: str, body: str, block: str | None) -> dict:
    """深入輪每頁正文落檔並登記；未 verify 前不得作為 fill 依據。"""
    ev = data["deep"].setdefault("evidence", [])
    d = evidence_dir()
    d.mkdir(parents=True, exist_ok=True)
    # 同目錄可有多本帳（補證輪另開新帳）；以帳本名區隔，避免編號從 001 重來蓋掉舊存證
    f = d / f"{ledger_path().stem.lstrip('.')}-{len(ev) + 1:03d}.txt"
    f.write_text(body, encoding="utf-8")
    rec = {"at": now_iso(), "cell": cell, "url": url, "path": str(f), "chars": len(body),
           "block": block, "verified": False, "quote": None}
    ev.append(rec)
    return rec


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower()


def do_verify(args, path):
    """原文摘錄必須逐字（空白正規化）出現在已落檔、未被判擋頁的正文中。"""
    data = load(path)
    if data["phase"] != "deep":
        print("ERROR verify only in phase deep")
        return 2
    q = _norm(args.quote)
    if len(q) < 8:
        print("ERROR quote too short (<8 chars)")
        return 2
    if args.cell not in data["deep"]["gaps"]:
        print(f"EXHAUSTED cell={args.cell} reason=not_a_gap")
        return 4
    # 存證屬於網址正文；同一頁在別格抓過也可引用，核實結果記在本格名下
    recs = [e for e in data["deep"].get("evidence", []) if e["url"] == args.url]
    if not recs:
        print(f"EXHAUSTED cell={args.cell} reason=no_evidence")
        return 4
    rec = recs[-1]
    if rec["block"]:
        print(f"EXHAUSTED cell={args.cell} reason=blocked_body:{rec['block']}")
        return 4
    try:
        body = Path(rec["path"]).read_text(encoding="utf-8")
    except OSError:
        print(f"EXHAUSTED cell={args.cell} reason=evidence_missing")
        return 4
    if q not in _norm(body):
        print(f"EXHAUSTED cell={args.cell} reason=quote_not_found")
        return 4
    if rec["cell"] != args.cell:
        rec = dict(rec, cell=args.cell)
        data["deep"]["evidence"].append(rec)
    rec["verified"], rec["quote"] = True, args.quote
    save(path, data)
    print(f"VERIFIED cell={args.cell} url={args.url}")
    return 0


def do_refund(args, path):
    """工具不可用（reach rc=3、camofox BROWSER_DOWN：沒拿到任何網路回應）退回剛扣的一單位。

    2026-10-05 實測：Exa 回 503 時 9 格各扣 1 次搜尋，搜尋總額一次燒掉一半卻零結果。
    查詢紀錄保留（hits=-1 供負面主張稽核），標 refunded 後不再算重複查詢，備援通道可用同一查詢。
    """
    data = load(path)
    cell, kind = args.cell, args.kind
    c = data["cells"].get(cell)
    if c is None:
        print(f"ERROR unknown cell={cell}")
        return 2
    if data["phase"] == "deep":
        # 深入輪是獨立額度（不動 totals），只退 deep.used
        used = data["deep"]["used"].get(cell, {})
        if used.get(kind, 0) <= 0:
            print(f"ERROR nothing to refund cell={cell} kind={kind}")
            return 2
        used[kind] -= 1
        data["refunds"] = data.get("refunds", 0) + 1
        save(path, data)
        print(f"REFUND kind={kind} cell={cell} phase=deep reason=tool_unavailable refunds={data['refunds']}")
        return 0
    if data["phase"] == "round2":
        key = f"r2c_{kind}" if args.channel == "camofox" else f"r2_{kind}"
    else:
        key = kind
    if c.get(key, 0) <= 0 or data["totals"][kind] <= 0:
        print(f"ERROR nothing to refund cell={cell} kind={kind}")
        return 2
    c[key] -= 1
    data["totals"][kind] -= 1
    if kind == "search" and c.get("queries"):
        c["queries"][-1]["hits"] = -1
        c["queries"][-1]["refunded"] = True
    data["refunds"] = data.get("refunds", 0) + 1
    save(path, data)
    print(f"REFUND kind={kind} cell={cell} reason=tool_unavailable refunds={data['refunds']}")
    return 0


def do_trail(args, path):
    """回填最近一筆查詢的命中數；帶 --q 則補登一筆（camofox／人工檢索走這條）。"""
    data = load(path)
    cell = args.cell
    if cell not in data["cells"]:
        print(f"ERROR unknown cell={cell}")
        return 2
    qs = data["cells"][cell].setdefault("queries", [])
    if args.q:
        qs.append({"at": now_iso(), "q": args.q, "hits": args.hits})
    elif qs:
        qs[-1]["hits"] = args.hits
    else:
        print(f"ERROR no query to stamp cell={cell} (pass --q to append one)")
        return 2
    save(path, data)
    print(f"TRAIL cell={cell} queries={len(qs)} hits={qs[-1]['hits']}")
    return 0


def do_nonew(args, path):
    data = load(path)
    cell = args.cell
    cells_ref = data["cells"]
    cells_ref[cell]["no_new"] += 1
    if cells_ref[cell]["no_new"] >= 2:
        cells_ref[cell]["state"] = "CLOSED"
    save(path, data)
    print(f"NONEW cell={cell} no_new={cells_ref[cell]['no_new']} state={cells_ref[cell]['state']}")
    return 0


def do_fill(args, path):
    data = load(path)
    cells_ref = data["cells"]
    cell = args.cell
    if data["phase"] == "deep" and cell in data["deep"]["gaps"]:
        if not any(e["cell"] == cell and e["verified"] for e in data["deep"].get("evidence", [])):
            print(f"EXHAUSTED cell={cell} reason=unverified")
            return 4
        deep_verified = True  # 逐字核實過的單一來源足以成立，不套 min_refs
    else:
        deep_verified = False
    cd = cells_ref[cell]
    # 「208,213,214」要拆成三筆；整串當一筆會讓下限閘少算（10040）
    for r in (s.strip() for s in (args.ref or "").split(",")):
        if r and r not in cd["refs"]:
            cd["refs"].append(r)
    # 舊帳本無 min_refs → 1，維持進行中調研的原語義
    need = data.get("min_refs", 1)
    sole = (getattr(args, "sole", None) or "").strip()
    if not deep_verified and not sole and len(cd["refs"]) < need:
        save(path, data)
        print(f"PARTIAL cell={cell} refs={len(cd['refs'])}/{need} (state={cd['state']}; "
              f"補第 2 個不同來源，或唯一一手來源用 --sole \"<理由>\")")
        return 0
    # 題目閘：登記過的必答題要逐題結案（有來源或 --none 理由）才 FILLED。
    # 舊版「答滿 3 題」只寫在 SKILL.md，實測 25/25 格 FILLED 但約 30% 題目沒有實質答案。
    open_q = [q["id"] for q in cd.get("questions", []) if q["state"] == "open"]
    if open_q and not deep_verified:
        save(path, data)
        print(f"PARTIAL cell={cell} refs={len(cd['refs'])}/{need} open_questions={','.join(open_q)} "
              f"(逐題 answer <格> <Q> <N>，查不到用 --none \"<理由>\")")
        return 0
    if sole:
        cd["sole_reason"] = sole
    cd["state"] = "FILLED"
    save(path, data)
    print(f"FILLED cell={cell} refs={len(cd['refs'])}")
    return 0


def do_ask(args, path):
    """登記本格必答問題（第一輪查詢的來源）；抓取額度隨題數放大，見 Q_FETCH_RATIO。"""
    data = load(path)
    cd = data["cells"].get(args.cell)
    if cd is None:
        print(f"ERROR unknown cell={args.cell}")
        return 2
    if data["phase"] != "round1":
        print(f"ERROR ask only in round1 (phase={data['phase']})")
        return 2
    qs = cd.setdefault("questions", [])
    seen = {q["q"].strip().lower() for q in qs}
    new = []
    for t in (s.strip() for s in args.question):
        if t and t.lower() not in seen:
            seen.add(t.lower())
            new.append(t)
    if len(qs) + len(new) > MAX_Q_PER_CELL:
        print(f"ERROR questions={len(qs) + len(new)} exceeds {MAX_Q_PER_CELL} per cell (拆格或合併題目)")
        return 2
    for t in new:
        qs.append({"id": f"Q{len(qs) + 1}", "q": t, "state": "open"})
    extra = q_fetch_extra(data, cd)
    data["total_fetch_cap"] += extra - cd.get("q_fetch", 0)
    cd["q_fetch"] = extra
    save(path, data)
    print(f"ASK cell={args.cell} questions={len(qs)} fetch_cap={cell_cap(data, cd, 'fetch')} "
          f"total_fetch_cap={data['total_fetch_cap']}")
    return 0


def do_answer(args, path):
    """逐題結案：有來源記 [N]；公開來源未見用 --none "<理由>"，找到候選頁沒抓就附 --cand <URL>。"""
    data = load(path)
    cd = data["cells"].get(args.cell)
    q = next((x for x in (cd or {}).get("questions", []) if x["id"] == args.qid), None)
    if q is None:
        print(f"ERROR unknown question cell={args.cell} id={args.qid}")
        return 2
    refs = [r.strip() for r in (args.ref or "").split(",") if r.strip()]
    none = (args.none or "").strip()
    if bool(refs) == bool(none):
        print("ERROR give either refs (N or N,M) or --none \"<理由>\"")
        return 2
    if args.cand and not none:
        print("ERROR --cand only with --none")
        return 2
    for k in ("refs", "reason", "cand"):
        q.pop(k, None)
    if refs:
        q.update(state="answered", refs=refs)
    else:
        q.update(state="none", reason=none)
        if args.cand:
            q["cand"] = args.cand
    save(path, data)
    left = sum(x["state"] == "open" for x in cd["questions"])
    print(f"ANSWER cell={args.cell} id={args.qid} state={q['state']} open_left={left}")
    return 0


def do_core(args, path):
    """登記核心決策問題：使用者這次調研指令真正要回答的那一題。

    逐格必答題回答的是「查什麼」，核心問題回答的是「為什麼查」。成稿時一句話結論必須
    正面回答它（validate_report.py --answer-map 機械核對），第三輪 unanswered 旗標審語意。
    """
    data = load(path)
    text = " ".join(args.question).strip()
    if not text:
        print("ERROR empty core question")
        return 2
    if data["phase"] == "final":
        print("ERROR core question is frozen after phase final")
        return 2
    data["core_question"] = text
    save(path, data)
    print(f"CORE {text}")
    return 0


def do_close(args, path):
    data = load(path)
    cell = args.cell
    data["cells"][cell]["state"] = "CLOSED"
    data["cells"][cell]["close_reason"] = args.reason or ""
    save(path, data)
    print(f"CLOSED cell={cell}")
    return 0


def do_entities(args, path):
    """Record the subject-resolution table (brand -> legal entities -> aliases).

    This is the D1 mandatory work product. D2/D6 spend is gated on it being
    non-empty (see cell_ok). One call appends one brand row; call repeatedly
    for multi-entity subjects. Legal names come from S2 terms/authorization
    pages (Limited/LLC/UAB), NOT the brand name.
    """
    data = load(path)
    row = {
        "brand": args.brand,
        "legal": [s for s in args.legal.split(",") if s],
        "aliases": [s for s in (args.aliases or "").split(",") if s],
        "former": [s for s in (args.former or "").split(",") if s],
        "people": [s for s in (args.people or "").split(",") if s],
    }
    data.setdefault("entities", []).append(row)
    save(path, data)
    names = row["legal"] + row["aliases"] + row["former"] + row["people"]
    print(f"ENTITIES brand={row['brand']} names={len(names)} total_rows={len(data['entities'])}")
    return 0


def do_gaps(args, path):
    data = load(path)
    need = data.get("min_refs", 1)
    for c in sorted(data["cells"]):
        cd = data["cells"][c]
        thin = cd["state"] == "CLOSED" and len(cd["refs"]) < need and not cd.get("sole_reason")
        if cd["state"] == "OPEN" or thin:
            print(f"{c}\t{cd['state']}\tfetch={cd['fetch']}\tsearch={cd['search']}\trefs={len(cd['refs'])}")
    # 題目層缺口：有候選頁沒抓的排最前（補最便宜），其次未結案，最後是確認查不到的
    rank = {"cand": 0, "open": 1, "none": 2}
    rows = []
    for c, cd in data["cells"].items():
        for q in cd.get("questions", []):
            if q["state"] == "answered":
                continue
            kind = "cand" if q.get("cand") else q["state"]
            rows.append((rank[kind], c, q["id"], kind, q.get("cand") or "-", q["q"]))
    for _, c, qid, kind, cand, text in sorted(rows):
        print(f"Q\t{c}\t{qid}\t{kind}\t{cand}\t{text}")
    return 0


def do_phase(args, path):
    data = load(path)
    if args.name == "round2":
        gaps = [s for s in (args.gaps or "").split(",") if s]
        if len(gaps) > data["max_gaps"]:
            print(f"ERROR gaps={len(gaps)} exceeds max_gaps={data['max_gaps']}")
            return 2
        data["phase"] = "round2"
        data["gaps"] = gaps
        for c in data["cells"]:
            if c not in gaps and data["cells"][c]["state"] == "OPEN":
                data["cells"][c]["state"] = "CLOSED"
        print(f"PHASE round2 gaps={len(gaps)}")
    elif args.name == "deep":
        # 只開一次：agent-reach 兩輪後仍有缺口才進；不是無限加碼的後門
        if data.get("deep"):
            print("ERROR deep round already run")
            return 2
        if data["phase"] == "round1":
            print("ERROR deep round requires agent-reach rounds first (phase=round1)")
            return 2
        gaps = [s for s in (args.gaps or "").split(",") if s]
        if not gaps or len(gaps) > data["max_gaps"]:
            print(f"ERROR gaps={len(gaps)} must be 1..max_gaps={data['max_gaps']}")
            return 2
        # --gaps 是格名清單不是數量；打錯會建出假格並把唯一一次深入輪燒掉
        unknown = [g for g in gaps if g not in data["cells"]]
        if unknown:
            print(f"ERROR unknown cells: {','.join(unknown)} (--gaps takes cell names, e.g. OKX/incidents)")
            return 2
        for g in gaps:
            data["cells"].setdefault(g, {"state": "OPEN", "fetch": 0, "search": 0, "no_new": 0,
                                         "bonus_fetch": 0, "bonus_search": 0, "refs": [],
                                         "r2_fetch": 0, "r2_search": 0})
            data["cells"][g]["state"] = "OPEN"
            data["cells"][g]["no_new"] = 0
        data["deep"] = {"gaps": gaps, "from": data["phase"], "started": now_iso(),
                        "fetch_per_gap": args.fetch_per_gap, "search_per_gap": args.search_per_gap,
                        "minutes": args.deep_minutes, "used": {}, "evidence": []}
        data["phase"] = "deep"
        print(f"PHASE deep gaps={len(gaps)} fetch_per_gap={args.fetch_per_gap} "
              f"search_per_gap={args.search_per_gap} minutes={args.deep_minutes}")
    else:
        # 定稿閘：新帳本必須登記核心問題，否則一句話結論沒有可核對的對象（舊帳本不設閘）
        if args.name == "final" and data.get("require_questions") and not data.get("core_question"):
            print("ERROR no core question; run: budget.py core \"<核心決策問題>\"")
            return 2
        data["phase"] = args.name
        print(f"PHASE {args.name}")
    save(path, data)
    return 0


def verdict(data) -> str:
    phase = data["phase"]
    cells = data["cells"]
    elapsed = (now_utc() - datetime.fromisoformat(data["created"])).total_seconds() / 60
    over = elapsed >= data["minutes"]
    if phase == "round1":
        open_cells = [c for c in cells if cells[c]["state"] == "OPEN"]
        budget_left = (data["totals"]["fetch"] < data["total_fetch_cap"]
                       or data["totals"]["search"] < data["total_search_cap"])
        if open_cells and budget_left and not over:
            return "continue"
        return "draft"
    if phase == "draft":
        return "round2" if data.get("gaps") else "round3"
    if phase == "round2":
        for c in data.get("gaps", []):
            if c in cells and (cells[c]["r2_fetch"] < 1 or cells[c]["r2_search"] < 1):
                if not over:
                    return "continue"
        return "integrate"
    if phase == "deep":
        d = data["deep"]
        dover = (now_utc() - datetime.fromisoformat(d["started"])).total_seconds() / 60 >= d["minutes"]
        for g in d["gaps"]:
            u = d["used"].get(g, {"fetch": 0, "search": 0})
            left = u["fetch"] < d["fetch_per_gap"] or u["search"] < d["search_per_gap"]
            if cells.get(g, {}).get("state") == "OPEN" and left and not dover:
                return "continue"
        return "integrate"
    if phase == "integrated":
        return "round3"
    return "finalize"


def do_status(args, path):
    data = load(path)
    elapsed = int((now_utc() - datetime.fromisoformat(data["created"])).total_seconds() / 60)
    print("CELL  state  fetch/cap  search/cap  refs")
    for c in sorted(data["cells"]):
        cd = data["cells"][c]
        refs = ",".join(cd["refs"]) or "-"
        fcap = cell_cap(data, cd, "fetch")
        scap = cell_cap(data, cd, "search")
        qs = cd.get("questions", [])
        qinfo = (f"  q=answered:{sum(q['state'] == 'answered' for q in qs)}"
                 f"/none:{sum(q['state'] == 'none' for q in qs)}/total:{len(qs)}") if qs else ""
        print(f"{c}  {cd['state']}  {cd['fetch']}/{fcap}  "
              f"{cd['search']}/{scap}  {refs}{qinfo}")
    print(f"totals fetch={data['totals']['fetch']}/{data['total_fetch_cap']} "
          f"search={data['totals']['search']}/{data['total_search_cap']}")
    print(f"reserve fetch={data['reserve_used_fetch']}/{data['reserve_fetch']} "
          f"search={data['reserve_used_search']}/{data['reserve_search']}")
    print(f"elapsed={elapsed}/{data['minutes']}")
    for t in data.get("topups", []):
        print(f"TOPUP {t['cell']} +fetch={t['fetch']} +search={t['search']} "
              f"+minutes={t['minutes']} reason={t['reason']}")
    ents = data.get("entities") or []
    if ents:
        print(f"entities={len(ents)} row(s): " + "; ".join(
            f"{r['brand']}->{','.join(r['legal'])}" for r in ents))
    else:
        print("entities=(none) — D2/D6 spend blocked until resolved")
    d = data.get("deep")
    if d:
        ev = d.get("evidence", [])
        used = ",".join(f"{g}:{d['used'].get(g, {}).get('fetch', 0)}/{d['fetch_per_gap']}f"
                        f"{d['used'].get(g, {}).get('search', 0)}/{d['search_per_gap']}s" for g in d["gaps"])
        print(f"deep gaps={len(d['gaps'])} used={used} evidence={len(ev)} "
              f"verified={sum(e['verified'] for e in ev)} blocked={sum(bool(e['block']) for e in ev)}")
    core = data.get("core_question")
    if core:
        print(f"core={core}")
    elif data.get("require_questions"):
        print("core=(none) — phase final blocked until `budget.py core` is run")
    print(f"NEXT: {verdict(data)}")
    return 0


def selftest() -> int:
    with tempfile.TemporaryDirectory() as td:
        env = os.environ.copy()
        env["RESEARCH_BUDGET"] = os.path.join(td, "t.json")
        path = Path(env["RESEARCH_BUDGET"])
        os.environ["RESEARCH_BUDGET"] = env["RESEARCH_BUDGET"]

        def run(argv):
            rc = main_core(argv)
            if argv[0] == "init" and rc == 0:  # 過題目閘；1 題不放大額度，不影響其他案的數字
                for c in load(path)["cells"]:
                    _capture(["ask", c, "q"])
                    _capture(["answer", c, "Q1", "0"])
            return rc

        # ① init 2x2 -> spend A/x fetch 3 OK, 4th 借保留池, 5th EXHAUSTED cell_cap
        if run(["init", "--platforms", "A,B", "--dims", "x,y"]) != 0:
            return _fail(1)
        for _ in range(5):
            code, out = _capture(["spend", "fetch", "A/x"])
        if not (code == 4 and "reason=cell_cap" in out):
            return _fail(1)

        # ② init --minutes 0 -> HALT time
        if run(["init", "--platforms", "A,B", "--dims", "x,y", "--minutes", "0"]) != 0:
            return _fail(2)
        code, out = _capture(["spend", "fetch", "A/x"])
        if not (code == 4 and "HALT time" in out):
            return _fail(2)

        # ③ fill all four -> NEXT: draft
        if run(["init", "--platforms", "A,B", "--dims", "x,y"]) != 0:
            return _fail(3)
        for c in ("A/x", "A/y", "B/x", "B/y"):
            run(["fill", c, "1"])
            run(["fill", c, "2"])
        code, out = _capture(["status"])
        if not out.strip().endswith("NEXT: draft"):
            return _fail(3)

        # ④ phase round2 --gaps with 11 gaps -> exit 2
        if run(["init", "--platforms", "A,B", "--dims", "x,y"]) != 0:
            return _fail(4)
        many = ",".join(f"A/c{i}" for i in range(11))
        code, _ = _capture(["phase", "round2", "--gaps", many])
        if code != 2:
            return _fail(4)

        # ⑤ nonew twice -> CLOSED
        if run(["init", "--platforms", "A", "--dims", "x"]) != 0:
            return _fail(5)
        run(["nonew", "A/x"]); code, out = _capture(["nonew", "A/x"])
        if not ("state=CLOSED" in out):
            return _fail(5)

        # ⑥ round2 gap spend fetch once OK, second cell_cap
        if run(["init", "--platforms", "A", "--dims", "x"]) != 0:
            return _fail(6)
        if run(["phase", "round2", "--gaps", "A/x"]) != 0:
            return _fail(6)
        code, _ = _capture(["spend", "fetch", "A/x"])
        if code != 0:
            return _fail(6)
        code, out = _capture(["spend", "fetch", "A/x"])
        if not (code == 4 and "reason=cell_cap" in out):
            return _fail(6)

        # ⑦ --mode vendor-dd presets: 4/6/6/150, and 7 gaps exceed max_gaps=6
        if run(["init", "--mode", "vendor-dd", "--platforms", "X", "--dims", "a"]) != 0:
            return _fail(7)
        led = load(path)
        if not (led["fetch_per_cell"] == 6 and led["search_per_cell"] == 4 and led["minutes"] == 150
                and led["max_gaps"] == 6 and led.get("mode") == "vendor-dd"):
            return _fail(7)
        code, _ = _capture(["phase", "round2", "--gaps", ",".join(f"X/g{i}" for i in range(7))])
        if code != 2:
            return _fail(7)

        # ⑧ entities gate: D2/D6 spend blocked until entities resolved, then OK
        if run(["init", "--mode", "vendor-dd", "--platforms", "X", "--dims", "D1,D2,D6"]) != 0:
            return _fail(8)
        code, out = _capture(["spend", "fetch", "X/D2"])
        if not (code == 4 and "reason=no_entities" in out):
            return _fail(8)
        code, out = _capture(["spend", "search", "X/D6"])
        if not (code == 4 and "reason=no_entities" in out):
            return _fail(8)
        # D1 is NOT gated — it's the cell that produces the entities table
        code, _ = _capture(["spend", "fetch", "X/D1"])
        if code != 0:
            return _fail(8)
        # resolve entities -> D2/D6 now spendable
        if run(["entities", "Interlace", "Qbitech,Bytechip LLC", "--former", "iPeakoin", "--people", "Yujun Wu"]) != 0:
            return _fail(8)
        code, _ = _capture(["spend", "fetch", "X/D2"])
        if code != 0:
            return _fail(8)
        code, _ = _capture(["spend", "search", "X/D6"])
        if code != 0:
            return _fail(8)

        # ⑨ topup 重開被 cell_cap 擋住的格：加碼後可再花，理由留痕；缺 --reason 由 argparse 擋
        # 3 格→保留池 2：自動借 1 後手動 topup 仍有 1
        if run(["init", "--platforms", "A,B,C", "--dims", "x"]) != 0:
            return _fail(9)
        while _capture(["spend", "fetch", "A/x"])[0] == 0:
            pass
        run(["close", "A/x", "channel:exit5"])
        code, out = _capture(["topup", "A/x", "--fetch", "1", "--reason", "gap+primary source http://x"])
        if not (code == 0 and "state=OPEN" in out):
            return _fail(9)
        code, _ = _capture(["spend", "fetch", "A/x"])
        if code != 0:
            return _fail(9)
        if load(path)["topups"][0]["reason"] != "gap+primary source http://x":
            return _fail(9)

        # ⑩ OPEN 格 topup 被拒 not_closed
        if run(["init", "--platforms", "A", "--dims", "x"]) != 0:
            return _fail(10)
        code, out = _capture(["topup", "A/x", "--fetch", "1", "--reason", "gap http://x"])
        if not (code == 4 and "reason=not_closed" in out):
            return _fail(10)

        # ⑪ 同格第二次 topup 被拒 already_topped
        if run(["init", "--platforms", "A", "--dims", "x"]) != 0:
            return _fail(11)
        run(["close", "A/x", "channel:exit5"])
        code, _ = _capture(["topup", "A/x", "--fetch", "1", "--reason", "gap http://x"])
        if code != 0:
            return _fail(11)
        run(["close", "A/x", "channel:exit5"])
        code, out = _capture(["topup", "A/x", "--fetch", "1", "--reason", "gap http://x2"])
        if not (code == 4 and "reason=already_topped" in out):
            return _fail(11)

        # ⑫ 保留池耗盡回 no_reserve
        if run(["init", "--platforms", "A,B", "--dims", "x"]) != 0:
            return _fail(12)
        run(["close", "A/x", "channel:exit5"])
        code, _ = _capture(["topup", "A/x", "--fetch", "1", "--reason", "gap http://x"])
        if code != 0:
            return _fail(12)
        run(["close", "B/x", "channel:exit5"])
        code, out = _capture(["topup", "B/x", "--fetch", "1", "--reason", "gap http://x"])
        if not (code == 4 and "reason=no_reserve" in out):
            return _fail(12)

        # ⑬ 同格同查詢第二次 duplicate_query
        if run(["init", "--platforms", "A", "--dims", "x"]) != 0:
            return _fail(13)
        code, _ = _capture(["spend", "search", "A/x", "--q", "Foo bar"])
        if code != 0:
            return _fail(13)
        code, out = _capture(["spend", "search", "A/x", "--q", " foo BAR "])
        if not (code == 4 and "reason=duplicate_query" in out):
            return _fail(13)

        # ⑭ round2：agent-reach 用掉 fetch 後，camofox 通道仍有自己的一次（兩通道各恰一次）
        if run(["init", "--platforms", "A", "--dims", "x,y"]) != 0:
            return _fail(14)
        run(["phase", "round2", "--gaps", "A/x"])
        if _capture(["spend", "fetch", "A/x"])[0] != 0:
            return _fail(14)
        if _capture(["spend", "fetch", "A/x", "--channel", "camofox"])[0] != 0:
            return _fail(14)
        code, out = _capture(["spend", "fetch", "A/x", "--channel", "camofox"])
        if not (code == 4 and "reason=cell_cap" in out):
            return _fail(14)

        # ⑮ deep 輪：總上限耗盡仍可花獨立額度；只准 camofox；到上限 deep_cap；不計 totals
        if run(["init", "--platforms", "A", "--dims", "x", "--fetch-per-cell", "1"]) != 0:
            return _fail(15)
        r1_used = 0  # 含自動借保留池的 1 單位
        while _capture(["spend", "fetch", "A/x"])[0] == 0:
            r1_used += 1
        if r1_used != 2:
            return _fail(15)
        code, _ = _capture(["phase", "deep", "--gaps", "A/x"])  # round1 不准直接進 deep
        if code != 2:
            return _fail(15)
        run(["phase", "draft"])
        if run(["phase", "deep", "--gaps", "A/x", "--fetch-per-gap", "2"]) != 0:
            return _fail(15)
        code, out = _capture(["spend", "fetch", "A/x"])
        if not (code == 4 and "reason=deep_camofox_only" in out):
            return _fail(15)
        for _ in range(2):
            if _capture(["spend", "fetch", "A/x", "--channel", "camofox"])[0] != 0:
                return _fail(15)
        code, out = _capture(["spend", "fetch", "A/x", "--channel", "camofox"])
        if not (code == 4 and "reason=deep_cap" in out):
            return _fail(15)
        if load(path)["totals"]["fetch"] != r1_used:
            return _fail(15)
        code, _ = _capture(["phase", "deep", "--gaps", "A/x"])  # 只開一次
        if code != 2:
            return _fail(15)

        # ⑯ deep 核實閘：未 verify 不得 fill；擋頁正文不得 verify；摘錄須逐字出現
        data = load(path)
        add_evidence(data, "A/x", "http://ok", "Header nav\n China  is listed as unsupported here.", None)
        add_evidence(data, "A/x", "http://blk", "Just a moment... checking", "marker")
        save(path, data)
        code, out = _capture(["fill", "A/x", "1"])
        if not (code == 4 and "reason=unverified" in out):
            return _fail(16)
        code, out = _capture(["verify", "A/x", "http://blk", "--quote", "Just a moment"])
        if not (code == 4 and "blocked_body" in out):
            return _fail(16)
        code, out = _capture(["verify", "A/x", "http://ok", "--quote", "Australia is listed"])
        if not (code == 4 and "reason=quote_not_found" in out):
            return _fail(16)
        if _capture(["verify", "A/x", "http://ok", "--quote", "china is LISTED as unsupported"])[0] != 0:
            return _fail(16)
        if _capture(["fill", "A/x", "1"])[0] != 0:
            return _fail(16)
        code, out = _capture(["status"])
        if not ("verified=1" in out and out.strip().endswith("NEXT: integrate")):
            return _fail(16)

        # ⑰ 跨格引用：同一 URL 在別格落檔，本格可 verify；非缺口格不得 verify
        if run(["init", "--platforms", "A", "--dims", "x,y", "--fetch-per-cell", "1"]) != 0:
            return _fail(17)
        run(["phase", "draft"])
        run(["phase", "deep", "--gaps", "A/x,A/y"])
        data = load(path)
        add_evidence(data, "A/x", "http://shared", "Visa and Mastercard are supported for card purchases.", None)
        save(path, data)
        if _capture(["verify", "A/y", "http://shared", "--quote", "Visa and Mastercard are supported"])[0] != 0:
            return _fail(17)
        if _capture(["fill", "A/y", "1"])[0] != 0:
            return _fail(17)
        code, out = _capture(["verify", "B/z", "http://shared", "--quote", "Visa and Mastercard"])
        if not (code == 4 and "reason=not_a_gap" in out):
            return _fail(17)

        # ⑱ 下限閘：1 個來源 PARTIAL 不轉 FILLED；同號重複不計；第 2 個不同來源才 FILLED；--sole 放行
        if run(["init", "--platforms", "A,B", "--dims", "x"]) != 0:
            return _fail(18)
        code, out = _capture(["fill", "A/x", "3"])
        if not (code == 0 and "PARTIAL" in out and load(path)["cells"]["A/x"]["state"] == "OPEN"):
            return _fail(18)
        if "PARTIAL" not in _capture(["fill", "A/x", "3"])[1]:
            return _fail(18)
        if "FILLED" not in _capture(["fill", "A/x", "4"])[1]:
            return _fail(18)
        code, out = _capture(["fill", "B/x", "5", "--sole", "唯一官方名冊頁"])
        if not ("FILLED" in out and load(path)["cells"]["B/x"]["sole_reason"] == "唯一官方名冊頁"):
            return _fail(18)
        # FILLED 不擋花費：格內額度內仍可補答（每格 3 抓），CLOSED 才擋
        if _capture(["spend", "fetch", "A/x"])[0] != 0:
            return _fail(18)
        run(["close", "B/x", "test"])
        if "reason=state_CLOSED" not in _capture(["spend", "fetch", "B/x"])[1]:
            return _fail(18)
        # 逗號串拆成多筆並去重：「7,8,7」= 2 筆，直接 FILLED
        run(["init", "--platforms", "A", "--dims", "x"])
        if "FILLED cell=A/x refs=2" not in _capture(["fill", "A/x", "7,8,7"])[1]:
            return _fail(18)
        # deep --gaps 收格名；未知格名（例如誤傳數量 1）拒絕，不建假格、不燒掉深入輪
        led = load(path); led["phase"] = "round2"; save(path, led)
        if _capture(["phase", "deep", "--gaps", "1"])[0] != 2 or "1" in load(path)["cells"] \
                or load(path).get("deep"):
            return _fail(18)

        # 自動借保留池：未 FILLED 格用完額度借 1 次；第 2 次與 FILLED 格不借
        run(["init", "--platforms", "A", "--dims", "x,y"])
        led = load(path)
        per = led["fetch_per_cell"]
        for _ in range(per):
            run(["spend", "fetch", "A/x"])
        if _capture(["spend", "fetch", "A/x"])[0] != 0 or load(path)["reserve_used_fetch"] != 1:
            return _fail(18)
        if "reason=cell_cap" not in _capture(["spend", "fetch", "A/x"])[1]:
            return _fail(18)
        run(["fill", "A/y", "1,2"])
        for _ in range(per):
            run(["spend", "fetch", "A/y"])
        if "reason=cell_cap" not in _capture(["spend", "fetch", "A/y"])[1] \
                or load(path)["reserve_used_fetch"] != 1:
            return _fail(18)

        # ⑲ 雙層上限：30 格不降額、總量吃 mode 天花板；42 格降為 2/2（搜尋不降到 1）
        run(["init", "--platforms", "A,B,C,D,E", "--dims", "a,b,c,d,e,f"])
        led = load(path)
        if not (led["fetch_per_cell"] == 3 and led["total_fetch_cap"] == 90
                and led["total_search_cap"] == 60):
            return _fail(19)
        run(["init", "--platforms", "A,B,C,D,E,F", "--dims", "a,b,c,d,e,f,g"])
        led = load(path)
        if not (led["fetch_per_cell"] == 2 and led["search_per_cell"] == 2
                and led["total_fetch_cap"] == 84 and led["total_search_cap"] == 80):
            return _fail(19)

        # ⑳ 保留池：額度用盡而關閉的格（非 channel:）可加碼；未用盡又非通道失敗的格拒 not_eligible
        run(["init", "--platforms", "A,B,C", "--dims", "x"])  # 保留池 2：自動借 1＋topup 1
        while _capture(["spend", "fetch", "A/x"])[0] == 0:
            pass
        run(["close", "A/x", "cell_cap"])
        if _capture(["topup", "A/x", "--fetch", "1", "--reason", "primary http://x"])[0] != 0:
            return _fail(20)
        run(["close", "B/x", "放棄"])
        code, out = _capture(["topup", "B/x", "--fetch", "1", "--reason", "http://y"])
        if not (code == 4 and "reason=not_eligible" in out):
            return _fail(20)

        # ㉑ gaps 列出來源不足而關閉的薄格
        run(["init", "--platforms", "A", "--dims", "x,y"])
        run(["fill", "A/x", "1"]); run(["close", "A/x", "cell_cap"])
        run(["fill", "A/y", "1"]); run(["fill", "A/y", "2"])
        code, out = _capture(["gaps"])
        if not ("A/x" in out and "A/y" not in out):
            return _fail(21)

        # ㉒ 工具掛掉退款：額度與總量回原值、同查詢可重送；退到 0 以下拒絕
        run(["init", "--platforms", "A", "--dims", "x,y"])
        run(["spend", "search", "A/x", "--q", "exa down"])
        if _capture(["refund", "search", "A/x"])[0] != 0:
            return _fail(22)
        led = load(path)
        if not (led["cells"]["A/x"]["search"] == 0 and led["totals"]["search"] == 0
                and led["cells"]["A/x"]["queries"][-1]["hits"] == -1):
            return _fail(22)
        if _capture(["spend", "search", "A/x", "--q", "exa down"])[0] != 0:
            return _fail(22)
        run(["spend", "fetch", "A/y"])
        if _capture(["refund", "fetch", "A/y"])[0] != 0 or _capture(["refund", "fetch", "A/y"])[0] != 2:
            return _fail(22)

        # ㉓ 深入輪退款：只退 deep.used，退到 0 以下拒絕
        run(["phase", "draft"])
        run(["phase", "deep", "--gaps", "A/x", "--fetch-per-gap", "2"])
        run(["spend", "fetch", "A/x", "--channel", "camofox"])
        if _capture(["refund", "fetch", "A/x", "--channel", "camofox"])[0] != 0:
            return _fail(23)
        if load(path)["deep"]["used"]["A/x"]["fetch"] != 0:
            return _fail(23)
        if _capture(["refund", "fetch", "A/x", "--channel", "camofox"])[0] != 2:
            return _fail(23)

        # ㉔ 題目追蹤：6 題 → 抓取額度 3→5、總上限同步加；未結案題擋 FILLED；--none 算結案；
        #    gaps 候選頁排最前；重複題不重登；超過 8 題拒；round1 以外不准 ask
        main_core(["init", "--platforms", "A,B", "--dims", "x,y"])  # 2 平台＝competitor 每格抓 3
        cap0 = load(path)["total_fetch_cap"]
        code, out = _capture(["ask", "A/x", "q1", "q2", "q3", "q4", "q5", "q6", "Q1 "])
        led = load(path)
        if not (code == 0 and "fetch_cap=5" in out and len(led["cells"]["A/x"]["questions"]) == 6
                and led["total_fetch_cap"] == cap0 + 2):
            return _fail(24)
        for _ in range(5):
            if _capture(["spend", "fetch", "A/x"])[0] != 0:
                return _fail(24)
        run(["fill", "A/x", "1,2"])
        if load(path)["cells"]["A/x"]["state"] != "OPEN":  # 來源夠但題目未結案
            return _fail(24)
        for i in range(1, 5):
            run(["answer", "A/x", f"Q{i}", "1"])
        run(["answer", "A/x", "Q5", "--none", "官網未列", "--cand", "http://cand"])
        code, out = _capture(["fill", "A/x"])
        if not ("open_questions=Q6" in out and load(path)["cells"]["A/x"]["state"] == "OPEN"):
            return _fail(24)
        run(["answer", "A/x", "Q6", "--none", "公開來源未見"])
        if "FILLED" not in _capture(["fill", "A/x"])[1]:
            return _fail(24)
        qlines = [l for l in _capture(["gaps"])[1].splitlines() if l.startswith("Q\t")]
        if not (len(qlines) == 2 and "\tQ5\tcand\thttp://cand\t" in qlines[0]):
            return _fail(24)
        if _capture(["answer", "A/x", "Q1", "1", "--none", "x"])[0] != 2 \
                or _capture(["answer", "A/x", "Q1", "1", "--cand", "http://x"])[0] != 2 \
                or _capture(["ask", "A/y"] + [f"t{i}" for i in range(9)])[0] != 2:
            return _fail(24)
        run(["phase", "draft"])
        if _capture(["ask", "A/y", "late"])[0] != 2:
            return _fail(24)
        # 沒登記題目的格維持舊語義（2 來源即 FILLED），舊帳本不受影響
        main_core(["init", "--platforms", "A,B", "--dims", "x"])
        if "FILLED" not in _capture(["fill", "A/x", "1,2"])[1]:
            return _fail(24)

        # ㉕ 題目閘：新帳本第一輪沒 ask 不准 spend（fetch／search 皆擋、不扣額度）；
        #    ask 後放行；舊帳本（無 require_questions 欄）不設閘
        main_core(["init", "--platforms", "A,B", "--dims", "x"])
        for kind in ("fetch", "search"):
            code, out = _capture(["spend", kind, "A/x"])
            if not (code == 4 and "reason=no_questions" in out):
                return _fail(25)
        if load(path)["totals"] != {"fetch": 0, "search": 0}:
            return _fail(25)
        _capture(["ask", "A/x", "誰負責審核"])
        if _capture(["spend", "fetch", "A/x"])[0] != 0 \
                or "reason=no_questions" not in _capture(["spend", "fetch", "B/x"])[1]:
            return _fail(25)
        led = load(path)
        led.pop("require_questions")
        save(path, led)
        if _capture(["spend", "fetch", "B/x"])[0] != 0:
            return _fail(25)

        # ㉖ 核心問題閘：新帳本沒登記 core 不准 phase final；登記後放行；final 後凍結；
        #    舊帳本（無 require_questions 欄）不設閘
        main_core(["init", "--platforms", "A", "--dims", "x"])
        code, out = _capture(["phase", "final"])
        if not (code == 2 and "no core question" in out and load(path)["phase"] == "round1"):
            return _fail(26)
        if _capture(["core", "  "])[0] != 2:
            return _fail(26)
        code, out = _capture(["core", "該廠商能否作為", "KYT", "供應商"])
        if not (code == 0 and load(path)["core_question"] == "該廠商能否作為 KYT 供應商"):
            return _fail(26)
        if "core=該廠商能否作為 KYT 供應商" not in _capture(["status"])[1]:
            return _fail(26)
        if _capture(["phase", "final"])[0] != 0 or _capture(["core", "改題"])[0] != 2:
            return _fail(26)
        main_core(["init", "--platforms", "A", "--dims", "x"])
        led = load(path)
        led.pop("require_questions")
        save(path, led)
        if _capture(["phase", "final"])[0] != 0:
            return _fail(26)

    print("SELFTEST PASS: budget ledger (26 cases)")
    return 0


def _fail(n):
    print(f"SELFTEST FAIL: case {n}")
    return 1


def _capture(argv) -> tuple[int, str]:
    import io
    old = sys.stdout
    sys.stdout = io.StringIO()
    try:
        rc = main_core(argv)
    finally:
        out = sys.stdout.getvalue()
        sys.stdout = old
    return rc, out


def do_topup(args, path):
    """定額加碼：重開單格並加配額，理由必填、全程留痕。

    停損語義是擋「同一問題無差別重刷」，不是「沒預算就不查證」。缺口明確且已鎖定
    一手來源時由主 session 加碼；蒐集代理不得自行呼叫本指令。
    """
    data = load(path)
    cell = args.cell
    if cell not in data["cells"]:
        if not getattr(args, "new", False):
            print(f"ERROR unknown cell: {cell} (pass --new to open it)", file=sys.stderr)
            return 2
        data["cells"][cell] = {
            "state": "OPEN", "fetch": 0, "search": 0, "no_new": 0,
            "bonus_fetch": 0, "bonus_search": 0,
            "refs": [], "r2_fetch": 0, "r2_search": 0,
        }
    if min(args.fetch, args.search, args.minutes) < 0:
        print("ERROR topup amounts must be >= 0", file=sys.stderr)
        return 2
    if args.fetch + args.search + args.minutes == 0:
        print("ERROR topup needs at least one of --fetch/--search/--minutes > 0", file=sys.stderr)
        return 2
    # 加碼前提：任一不符即拒（EXHAUSTED），不動 ledger
    # already_topped 先於 not_closed：topup 成功後格回 OPEN，同格再 topup 仍算已加碼過
    if any(t.get("cell") == cell for t in data.get("topups", [])):
        print(f"EXHAUSTED cell={cell} reason=already_topped")
        return 4
    if cell not in data["cells"] or data["cells"][cell]["state"] != "CLOSED":
        print(f"EXHAUSTED cell={cell} reason=not_closed")
        return 4
    # 保留池＝尾款（借鏡 jina node-DeepResearch 的 beast mode 保留額度）：通道失敗或
    # 該格額度已用盡的格都可動用；舊版只認 channel: 前提，實測 0 次被用到。
    cd0 = data["cells"][cell]
    capped = (cd0["fetch"] >= cell_cap(data, cd0, "fetch")
              or cd0["search"] >= cell_cap(data, cd0, "search"))
    if not (str(cd0.get("close_reason", "")).startswith("channel:") or capped):
        print(f"EXHAUSTED cell={cell} reason=not_eligible")
        return 4
    if "http" not in (args.reason or ""):
        print(f"EXHAUSTED cell={cell} reason=no_source_url")
        return 4
    if args.fetch > (data["reserve_fetch"] - data["reserve_used_fetch"]) \
            or args.search > (data["reserve_search"] - data["reserve_used_search"]):
        print(f"EXHAUSTED cell={cell} reason=no_reserve")
        return 4
    cd = data["cells"][cell]
    cd["bonus_fetch"] = cd.get("bonus_fetch", 0) + args.fetch
    cd["bonus_search"] = cd.get("bonus_search", 0) + args.search
    cd["state"] = "OPEN"
    cd["no_new"] = 0
    data["total_fetch_cap"] += args.fetch
    data["total_search_cap"] += args.search
    data["reserve_used_fetch"] += args.fetch
    data["reserve_used_search"] += args.search
    data["minutes"] += args.minutes
    if data["phase"] not in ("round1", "round2"):
        data["phase"] = "round1"
    data.setdefault("topups", []).append({
        "at": now_iso(), "cell": cell, "fetch": args.fetch,
        "search": args.search, "minutes": args.minutes, "reason": args.reason,
    })
    save(path, data)
    print(f"TOPUP cell={cell} +fetch={args.fetch} +search={args.search} "
          f"+minutes={args.minutes} phase={data['phase']} state=OPEN reason={args.reason}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="budget.py")
    sub = p.add_subparsers(dest="cmd", required=True)
    i = sub.add_parser("init")
    i.add_argument("--platforms", required=True)
    i.add_argument("--dims", required=True)
    i.add_argument("--mode", choices=tuple(MODE_PRESETS), default=None)
    i.add_argument("--fetch-per-cell", type=int, default=None)
    i.add_argument("--search-per-cell", type=int, default=None)
    i.add_argument("--max-gaps", type=int, default=None)
    i.add_argument("--minutes", type=int, default=None)
    i.set_defaults(func=do_init)
    s = sub.add_parser("spend")
    s.add_argument("kind", choices=("fetch", "search"))
    s.add_argument("cell")
    s.add_argument("--q", default=None, help="查詢詞；kind=search 時記入 cells[cell].queries")
    s.add_argument("--channel", choices=("reach", "camofox"), default="reach")
    s.set_defaults(func=do_spend)
    rf = sub.add_parser("refund")
    rf.add_argument("kind", choices=("fetch", "search"))
    rf.add_argument("cell")
    rf.add_argument("--channel", choices=("reach", "camofox"), default="reach")
    rf.set_defaults(func=do_refund)
    tr = sub.add_parser("trail")
    tr.add_argument("cell")
    tr.add_argument("--hits", type=int, default=None)
    tr.add_argument("--q", default=None)
    tr.set_defaults(func=do_trail)
    for name, fn in (("nonew", do_nonew), ("fill", do_fill), ("close", do_close)):
        x = sub.add_parser(name)
        x.add_argument("cell")
        if name == "fill":
            x.add_argument("ref", nargs="?")
            x.add_argument("--sole", default=None, help="唯一一手來源時的理由；免 min_refs")
        elif name == "nonew":
            x.add_argument("reason", nargs="*")
        else:
            x.add_argument("reason", nargs="?", default="")
        x.set_defaults(func=fn)
    tu = sub.add_parser("topup")
    tu.add_argument("cell")
    tu.add_argument("--fetch", type=int, default=0)
    tu.add_argument("--search", type=int, default=0)
    tu.add_argument("--minutes", type=int, default=0)
    tu.add_argument("--new", action="store_true", help="該 cell 不在矩陣內時明確開一格")
    tu.add_argument("--reason", required=True)
    tu.set_defaults(func=do_topup)
    a = sub.add_parser("ask")
    a.add_argument("cell")
    a.add_argument("question", nargs="+")
    a.set_defaults(func=do_ask)
    co = sub.add_parser("core")
    co.add_argument("question", nargs="+")
    co.set_defaults(func=do_core)
    an = sub.add_parser("answer")
    an.add_argument("cell")
    an.add_argument("qid")
    an.add_argument("ref", nargs="?")
    an.add_argument("--none", default=None, help="公開來源未見的理由")
    an.add_argument("--cand", default=None, help="找到但沒抓的候選網址（第二輪優先補）")
    an.set_defaults(func=do_answer)
    g = sub.add_parser("gaps"); g.set_defaults(func=do_gaps)
    e = sub.add_parser("entities")
    e.add_argument("brand")
    e.add_argument("legal")
    e.add_argument("--aliases", default="")
    e.add_argument("--former", default="")
    e.add_argument("--people", default="")
    e.set_defaults(func=do_entities)
    ph = sub.add_parser("phase")
    ph.add_argument("name", choices=("round2", "deep", "draft", "integrated", "round3", "final"))
    ph.add_argument("--gaps", default="")
    ph.add_argument("--fetch-per-gap", type=int, default=4)
    ph.add_argument("--search-per-gap", type=int, default=2)
    ph.add_argument("--deep-minutes", type=int, default=30)
    vf = sub.add_parser("verify")
    vf.add_argument("cell")
    vf.add_argument("url")
    vf.add_argument("--quote", required=True)
    vf.set_defaults(func=do_verify)
    ph.set_defaults(func=do_phase)
    st = sub.add_parser("status"); st.set_defaults(func=do_status)
    return p


def main_core(argv) -> int:
    if "--selftest" in argv:
        return selftest()
    args = build_parser().parse_args(argv)
    path = ledger_path()
    with ledger_lock(path):
        if args.cmd == "init":
            return args.func(args, path)
        if not path.exists():
            print("ERROR no ledger; run init first", file=sys.stderr)
            return 2
        return args.func(args, path)


if __name__ == "__main__":
    raise SystemExit(main_core(sys.argv[1:]))