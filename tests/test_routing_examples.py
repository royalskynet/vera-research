#!/usr/bin/env python3

from __future__ import annotations

import importlib.util
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("research_route", ROOT / "scripts" / "route.py")
assert SPEC and SPEC.loader
ROUTE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = ROUTE
SPEC.loader.exec_module(ROUTE)


def load_examples() -> list[tuple[str, set[str]]]:
    """Parse routing-examples.md table rows -> (query, expected capability set)."""
    text = (ROOT / "references" / "routing-examples.md").read_text()
    rows = []
    for line in text.splitlines():
        if not line.startswith("|") or line.startswith("|---"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 3:
            continue
        query = cells[0]
        route_cell = cells[2]
        m = re.search(r"`([^`]+)`", route_cell)
        if not m:
            continue
        expected = {cap.strip() for cap in m.group(1).split(" + ")}
        rows.append((query, expected))
    return rows


def _selected(query: str) -> set[str]:
    plan = ROUTE.build_plan(ROUTE.infer_profile(query))
    return {item["capability"] for item in plan["selected"]}


EXAMPLES = load_examples()


def _make_test(query: str, expected: set[str]) -> callable:
    def test(self: unittest.TestCase) -> None:
        self.assertEqual(expected, _selected(query))

    test.__name__ = f"test_example_{query[:8].strip()}"
    return test


class RoutingExamplesTest(unittest.TestCase):
    def test_examples_table_is_parsed(self) -> None:
        self.assertGreater(len(EXAMPLES), 5)


def _build_methods() -> dict[str, callable]:
    methods: dict[str, callable] = {}
    for query, expected in EXAMPLES:
        test = _make_test(query, expected)
        methods[test.__name__] = test
    return methods


for _name, _fn in _build_methods().items():
    setattr(RoutingExamplesTest, _name, _fn)

if __name__ == "__main__":
    unittest.main()
