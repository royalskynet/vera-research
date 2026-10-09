#!/usr/bin/env python3
"""Checkpoint and verify resumable deep/large research runs."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path


MANIFEST_NAME = "research-run.json"
VERDICTS = ("PASS", "WARN", "FAIL", "NOT_APPLICABLE", "BLOCKED", "ERROR")


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def manifest_path(run_dir: str) -> Path:
    return Path(run_dir).expanduser().resolve() / MANIFEST_NAME


def load(path: Path) -> dict:
    if not path.is_file():
        raise SystemExit(f"manifest not found: {path}")
    return json.loads(path.read_text())


def atomic_save(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=".research-run.", suffix=".json", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def do_init(args: argparse.Namespace) -> int:
    route_path = Path(args.route).expanduser().resolve()
    route_raw = route_path.read_bytes()
    route = json.loads(route_raw)
    if route.get("version") != 2:
        raise SystemExit("route plan must use contract version 2")
    path = manifest_path(args.run_dir)
    if path.exists():
        if args.resume:
            print(path)
            return 0
        raise SystemExit(f"manifest already exists: {path}; use --resume")

    phases: dict[str, dict] = {}
    for item in route.get("execution", []):
        phase = item["phase"]
        phases.setdefault(
            phase,
            {"status": "PENDING", "capability": item["capability"], "artifacts": {}, "summary": ""},
        )
    manifest = {
        "schema_version": 1,
        "created_at": now(),
        "updated_at": now(),
        "query_hash": sha256_bytes(route.get("profile", {}).get("query", "").encode()),
        "route_hash": sha256_bytes(route_raw),
        "route": route,
        "phases": phases,
        "events": [],
    }
    atomic_save(path, manifest)
    print(path)
    return 0


def do_checkpoint(args: argparse.Namespace) -> int:
    path = manifest_path(args.run_dir)
    manifest = load(path)
    if args.phase not in manifest["phases"]:
        known = ", ".join(manifest["phases"])
        raise SystemExit(f"unknown phase: {args.phase}; known: {known}")

    artifacts: dict[str, str] = {}
    for raw in args.artifact:
        artifact = Path(raw).expanduser().resolve()
        if not artifact.is_file():
            raise SystemExit(f"artifact not found: {artifact}")
        artifacts[str(artifact)] = sha256_file(artifact)

    timestamp = now()
    manifest["phases"][args.phase] = {
        "status": args.verdict,
        "capability": manifest["phases"][args.phase]["capability"],
        "artifacts": artifacts,
        "summary": args.summary,
        "updated_at": timestamp,
    }
    manifest["events"].append(
        {"at": timestamp, "phase": args.phase, "verdict": args.verdict, "summary": args.summary}
    )
    manifest["updated_at"] = timestamp
    atomic_save(path, manifest)
    print(f"{args.phase}={args.verdict}")
    return 0


def audit_status(manifest: dict) -> dict:
    phases = {}
    for phase, record in manifest["phases"].items():
        verdict = record["status"]
        stale = []
        for raw_path, expected in record.get("artifacts", {}).items():
            artifact = Path(raw_path)
            actual = sha256_file(artifact) if artifact.is_file() else "MISSING"
            if actual != expected:
                stale.append({"path": raw_path, "expected": expected, "actual": actual})
        phases[phase] = {"verdict": "STALE" if stale else verdict, "stale_artifacts": stale}

    assurance = manifest["route"].get("assurance", {})
    blocking = set(assurance.get("blocking_verdicts", []))
    effective = [item["verdict"] for item in phases.values()]
    if "MISSING" in blocking and "PENDING" in effective:
        overall = "BLOCKED"
    elif any(verdict in blocking for verdict in effective):
        overall = "BLOCKED"
    elif all(verdict in {"PASS", "WARN", "NOT_APPLICABLE"} for verdict in effective):
        overall = "PASS"
    else:
        overall = "IN_PROGRESS"
    return {"overall": overall, "assurance": assurance.get("level"), "phases": phases}


def do_status(args: argparse.Namespace) -> int:
    manifest = load(manifest_path(args.run_dir))
    result = audit_status(manifest)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if result["overall"] == "BLOCKED" else 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init")
    init.add_argument("--route", required=True)
    init.add_argument("--run-dir", required=True)
    init.add_argument("--resume", action="store_true")
    init.set_defaults(func=do_init)

    checkpoint = sub.add_parser("checkpoint")
    checkpoint.add_argument("--run-dir", required=True)
    checkpoint.add_argument("--phase", required=True)
    checkpoint.add_argument("--verdict", required=True, choices=VERDICTS)
    checkpoint.add_argument("--artifact", action="append", default=[])
    checkpoint.add_argument("--summary", default="")
    checkpoint.set_defaults(func=do_checkpoint)

    status = sub.add_parser("status")
    status.add_argument("--run-dir", required=True)
    status.set_defaults(func=do_status)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    raise SystemExit(args.func(args))


if __name__ == "__main__":
    main()
