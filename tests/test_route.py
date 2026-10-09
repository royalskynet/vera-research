#!/usr/bin/env python3

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("research_route", ROOT / "scripts" / "route.py")
assert SPEC and SPEC.loader
ROUTE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = ROUTE
SPEC.loader.exec_module(ROUTE)


def profile_from_dict(raw: dict) -> object:
    return ROUTE.TaskProfile(
        query=raw.get("query", ""),
        source_scopes=tuple(raw.get("source_scopes", ("web",))),
        freshness=raw.get("freshness", "current"),
        days=raw.get("days"),
        rigor=raw.get("rigor", "lookup"),
        complexity=raw.get("complexity", "simple"),
        privacy=tuple(raw.get("privacy", ("public",))),
        deliverable=raw.get("deliverable", "answer"),
        risk=raw.get("risk", "normal"),
        targets=tuple(raw.get("targets", ())),
        official_verification=raw.get("official_verification", False),
        authorized_external_actions=raw.get("authorized_external_actions", False),
        classification_confidence=raw.get("classification_confidence", "high"),
        explicit_capabilities=tuple(raw.get("explicit_capabilities", ())),
        research_kind=raw.get("research_kind", "general"),
        assurance=raw.get("assurance", "auto"),
    )


class RouteFixturesTest(unittest.TestCase):
    def test_fixtures(self) -> None:
        fixtures = json.loads((ROOT / "tests" / "fixtures" / "routes.json").read_text())
        for fixture in fixtures:
            with self.subTest(fixture=fixture["name"]):
                if "query" in fixture:
                    profile = ROUTE.infer_profile(fixture["query"])
                else:
                    profile = profile_from_dict(fixture["profile"])
                available = fixture.get("available")
                plan = ROUTE.build_plan(profile, None if available is None else set(available))
                selected = [item["capability"] for item in plan["selected"]]
                self.assertEqual(fixture["expected"], selected)
                self.assertEqual(fixture["expected_intensity"], plan["intensity"])
                if "expected_assurance" in fixture:
                    self.assertEqual(fixture["expected_assurance"], plan["assurance"]["level"])
                if "expected_days" in fixture:
                    self.assertEqual(fixture["expected_days"], plan["profile"]["days"])
                if "expected_gate" in fixture:
                    self.assertIn(fixture["expected_gate"], [gate["type"] for gate in plan["gates"]])
                if "expected_missing" in fixture:
                    self.assertEqual(fixture["expected_missing"], plan["missing"])

    def test_deep_execution_wraps_source_lanes(self) -> None:
        plan = ROUTE.build_plan(
            ROUTE.TaskProfile(
                source_scopes=("web", "recent-social"),
                rigor="deep",
                complexity="large",
                deliverable="report",
            )
        )
        self.assertEqual({"capability": "research-router", "phase": "classify-and-gate"}, plan["execution"][0])
        self.assertEqual({"capability": "deep-research", "phase": "synthesize-validate-package"}, plan["execution"][-1])

    def test_quick_path_skips_deep_engine(self) -> None:
        plan = ROUTE.build_plan(ROUTE.infer_profile("摘要這個網址 https://example.com"))
        self.assertEqual("quick", plan["intensity"])
        self.assertNotIn("deep-research", [item["capability"] for item in plan["selected"]])

    def test_unknown_availability_is_not_missing(self) -> None:
        plan = ROUTE.build_plan(ROUTE.infer_profile("研究一下 observability"))
        self.assertFalse(plan["availability_checked"])
        self.assertEqual([], plan["missing"])
        self.assertTrue(all(item["available"] is None for item in plan["selected"]))

    def test_native_deep_engine_is_always_available(self) -> None:
        plan = ROUTE.build_plan(ROUTE.infer_profile("研究一下 observability"), {"agent-reach"})
        deep = next(item for item in plan["selected"] if item["capability"] == "deep-research")
        self.assertTrue(deep["available"])
        self.assertNotIn("deep-research", plan["missing"])

    def test_cli_accepts_natural_language_query(self) -> None:
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "route.py"), "最近 14 天 Reddit 怎麼評價 Rust？"],
            check=True,
            capture_output=True,
            text=True,
        )
        payload = json.loads(result.stdout)
        self.assertEqual(2, payload["version"])
        self.assertEqual(14, payload["profile"]["days"])
        self.assertEqual("last30days", payload["selected"][0]["capability"])

    def test_low_confidence_needs_clarification_within_three(self) -> None:
        plan = ROUTE.build_plan(ROUTE.TaskProfile(classification_confidence="low"))
        c = plan["clarification"]
        self.assertTrue(c["needed"])
        self.assertLessEqual(len(c["questions"]), 3)
        self.assertEqual(len(c["questions"]), len(c["assumptions"]))

    def test_lookup_does_not_need_clarification(self) -> None:
        plan = ROUTE.build_plan(ROUTE.infer_profile("摘要這個 URL https://example.com"))
        self.assertFalse(plan["clarification"]["needed"])

    def test_invalid_explicit_capability_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            ROUTE.build_plan(ROUTE.TaskProfile(explicit_capabilities=("unknown",)))


if __name__ == "__main__":
    unittest.main()
