"""Search stored decisions for similar incidents. Counts come only from records."""

from __future__ import annotations

import json
from collections import Counter
from functools import lru_cache
from pathlib import Path

from f1_penalty_decoder.parse_decision import (
    COMPETITIVE_SESSION_TYPES,
    session_label,
    session_type_for_record,
)

ROOT = Path(__file__).resolve().parents[2]
DATA_PATH = ROOT / "data" / "decisions.json"


@lru_cache(maxsize=1)
def load_decisions() -> list[dict]:
    if not DATA_PATH.exists():
        return []
    payload = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    return [annotate_session(item) for item in payload.get("decisions") or []]


def annotate_session(item: dict) -> dict:
    """Copy a row and attach a session type. The file on disk is not written."""
    row = dict(item)
    kind = session_type_for_record(row)
    row["session_type"] = kind
    label = session_label(kind)
    row["session_label"] = label or (row.get("session") or "")
    return row


def is_competitive(item: dict) -> bool:
    kind = item.get("session_type") or session_type_for_record(item)
    return kind in COMPETITIVE_SESSION_TYPES


def reload_decisions() -> list[dict]:
    load_decisions.cache_clear()
    return load_decisions()


def search_precedents(
    decisions: list[dict],
    incident_type: str,
    *,
    penalty_kind: str = "",
    exclude_id: str = "",
    limit: int = 8,
) -> dict:
    """Count similar competitive-session cases and list a few examples.

    Practice sessions and rows with an unknown session are not counted.
    ``same_penalty`` is the number of matches whose ``penalty_kind`` equals
    the query. It is 0 when the query kind is empty or ``unknown``.
    """
    if not incident_type or incident_type == "other":
        pool = []
    else:
        pool = [
            item
            for item in decisions
            if item.get("incident_type") == incident_type
            and item.get("id") != exclude_id
            and is_competitive(item)
        ]
    kinds = Counter(item.get("penalty_kind") or "unknown" for item in pool)
    same = kinds.get(penalty_kind, 0) if penalty_kind and penalty_kind != "unknown" else 0
    examples = pool[:limit]
    return {
        "incident_type": incident_type,
        "similar_count": len(pool),
        "same_penalty_count": same,
        "penalty_kind": penalty_kind,
        "penalty_breakdown": dict(kinds),
        "examples": examples,
    }
