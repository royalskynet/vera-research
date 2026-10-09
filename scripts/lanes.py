#!/usr/bin/env python3
"""Capability registry + availability probes.

The lane list and probes are the single source of truth for router
capabilities.  Probe output is a snapshot at call time, not a guarantee.
"""

from __future__ import annotations

import argparse
import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


@dataclass(frozen=True)
class Lane:
    fallback: str
    probe: Callable[[], tuple[str, str]]


def _which_probe(binary: str) -> tuple[str, str]:
    how = f"shutil.which({binary!r})"
    return ("ok" if shutil.which(binary) else "off", how)


def _skill_probe(name: str) -> tuple[str, str]:
    how = f"Path.home()/.claude/skills/{name}/SKILL.md exists"
    path = Path.home() / ".claude" / "skills" / name / "SKILL.md"
    return ("ok" if path.is_file() else "off", how)


LANES: dict[str, Lane] = {
    "qmd": Lane(
        fallback=(
            "Use local rg over explicitly scoped Markdown files; disclose that "
            "semantic and hybrid retrieval are unavailable."
        ),
        probe=lambda: _which_probe("qmd"),
    ),
    "agent-reach": Lane(
        fallback=(
            "Use the host's built-in web search/fetch tools; authenticated "
            "platforms remain unavailable."
        ),
        probe=lambda: _which_probe("agent-reach"),
    ),
    "last30days": Lane(
        fallback=(
            "Use agent-reach for a bounded recent-source search; disclose that "
            "engagement weighting and cross-platform trend scoring are unavailable."
        ),
        probe=lambda: _skill_probe("last30days"),
    ),
    "user-research": Lane(
        fallback=(
            "Limit work to study planning or synthesis of user-provided material; "
            "do not claim participant contact or recruitment."
        ),
        probe=lambda: _skill_probe("user-research"),
    ),
    "deep-research": Lane(
        fallback=(
            "Use this project's native Vera scope, coverage, evidence, "
            "contradiction, critique, delta-query, and validation pipeline."
        ),
        probe=lambda: ("ok", "native (always ok)"),
    ),
}


def probe_all() -> dict[str, dict[str, str]]:
    return {name: dict(zip(("status", "how"), lane.probe())) for name, lane in LANES.items()}


def print_table(rows: dict[str, dict[str, str]]) -> None:
    width = max(len(name) for name in rows)
    for name, info in rows.items():
        print(f"{name:<{width}}  {info['status']:<3}  {info['how']}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    doctor = sub.add_parser("doctor", help="Probe all lanes and report availability.")
    doctor.add_argument("--json", action="store_true", help="Print machine-readable JSON snapshot.")
    args = parser.parse_args()

    if args.command != "doctor":
        parser.error("only subcommand supported: doctor")
    rows = probe_all()
    if args.json:
        payload = {name: {"status": r["status"], "how": r["how"]} for name, r in rows.items()}
        payload["snapshot"] = True
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print_table(rows)


if __name__ == "__main__":
    main()
