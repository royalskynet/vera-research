#!/usr/bin/env python3

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from lanes import LANES  # noqa: E402


SPEC = importlib.util.spec_from_file_location("research_route", ROOT / "scripts" / "route.py")
assert SPEC and SPEC.loader
ROUTE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = ROUTE
SPEC.loader.exec_module(ROUTE)


class LanesTest(unittest.TestCase):
    def test_order_matches_route(self) -> None:
        self.assertEqual(tuple(LANES), ROUTE.CAPABILITY_ORDER)

    def test_every_lane_in_capabilities_doc(self) -> None:
        text = (ROOT / "references" / "capabilities.md").read_text()
        for name in LANES:
            with self.subTest(lane=name):
                self.assertIn(name, text)

    def test_doctor_json_has_all_keys(self) -> None:
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "lanes.py"), "doctor", "--json"],
            check=True,
            capture_output=True,
            text=True,
        )
        payload = json.loads(result.stdout)
        self.assertIs(True, payload["snapshot"])
        self.assertEqual(
            {"qmd", "agent-reach", "last30days", "user-research", "deep-research"},
            {k for k in payload if k != "snapshot"},
        )


if __name__ == "__main__":
    unittest.main()
