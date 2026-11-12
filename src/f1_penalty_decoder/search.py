"""Search stored decisions for similar incidents. Counts come only from records."""

from __future__ import annotations

import json
from collections import Counter
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA_PATH = ROOT / "data" / "decisions.json"


@lru_cache(maxsize=1)
def load_decisions() -> list[dict]:
    if not DATA_PATH.exists():
        return []
    payload = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    return list(payload.get("decisions") or [])


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
    """Count similar cases and list a few examples.

    ``same_penalty`` is the number of matches whose ``penalty_kind`` equals
    the query. It is 0 when the query kind is empty or ``unknown``.
    """
    if not incident_type or incident_type == "other":
        pool = []
    else:
        pool = [
            item
            for item in decisions
            if item.get("incident_type") == incident_type and item.get("id") != exclude_id
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
