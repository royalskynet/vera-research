#!/usr/bin/env python3

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("research_run_state", ROOT / "scripts" / "run_state.py")
assert SPEC and SPEC.loader
STATE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = STATE
SPEC.loader.exec_module(STATE)


class RunStateTest(unittest.TestCase):
    def route(self) -> dict:
        return {
            "version": 2,
            "profile": {"query": "vendor background check"},
            "assurance": {"level": "audit", "blocking_verdicts": ["FAIL", "BLOCKED", "ERROR", "STALE", "MISSING"]},
            "execution": [
                {"capability": "research-router", "phase": "classify-and-gate"},
                {"capability": "deep-research", "phase": "scope-plan-coverage"},
            ],
        }

    def test_checkpoint_and_stale_detection(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            route_path = base / "route.json"
            route_path.write_text(json.dumps(self.route()))
            run_dir = base / "run"
            self.assertEqual(0, STATE.do_init(Namespace(route=str(route_path), run_dir=str(run_dir), resume=False)))

            artifact = base / "evidence.jsonl"
            artifact.write_text("one\n")
            self.assertEqual(
                0,
                STATE.do_checkpoint(
                    Namespace(
                        run_dir=str(run_dir),
                        phase="classify-and-gate",
                        verdict="PASS",
                        artifact=[str(artifact)],
                        summary="classified",
                    )
                ),
            )
            manifest = STATE.load(STATE.manifest_path(str(run_dir)))
            self.assertEqual("BLOCKED", STATE.audit_status(manifest)["overall"])

            artifact.write_text("changed\n")
            status = STATE.audit_status(manifest)
            self.assertEqual("STALE", status["phases"]["classify-and-gate"]["verdict"])
            self.assertEqual("BLOCKED", status["overall"])

    def test_all_green_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            route_path = base / "route.json"
            route_path.write_text(json.dumps(self.route()))
            run_dir = base / "run"
            STATE.do_init(Namespace(route=str(route_path), run_dir=str(run_dir), resume=False))
            for phase in ("classify-and-gate", "scope-plan-coverage"):
                STATE.do_checkpoint(
                    Namespace(run_dir=str(run_dir), phase=phase, verdict="PASS", artifact=[], summary="ok")
                )
            manifest = STATE.load(STATE.manifest_path(str(run_dir)))
            self.assertEqual("PASS", STATE.audit_status(manifest)["overall"])


if __name__ == "__main__":
    unittest.main()
