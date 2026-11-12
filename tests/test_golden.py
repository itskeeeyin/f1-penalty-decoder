"""Golden checks against real stewards' text stored in tests/golden.json.

Each example is an excerpt copied from a public decision PDF, plus the article,
penalty tag, and incident tag a reader should get from that excerpt. The test
fails if the parser's labels drift.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from f1_penalty_decoder.parse_decision import parse_decision_text

GOLDEN = json.loads((Path(__file__).parent / "golden.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("example", GOLDEN, ids=lambda item: item["id"])
def test_golden_labels(example):
    parsed = parse_decision_text(example["text"], example.get("title") or "")
    assert parsed["article"] == example["article"]
    assert parsed["penalty_kind"] == example["penalty_kind"]
    assert parsed["incident_type"] == example["incident_type"]
    if example.get("car_number"):
        assert parsed["car_number"] == example["car_number"]
