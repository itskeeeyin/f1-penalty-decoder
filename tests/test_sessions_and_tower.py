"""Competitive-session scope, tower HTML, and timing-table prose."""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

from f1_penalty_decoder.explain import explain_decision
from f1_penalty_decoder.search import is_competitive, load_decisions, search_precedents

ROOT = Path(__file__).resolve().parents[1]


def test_tower_html_has_no_indented_lines():
    os.environ.setdefault("STREAMLIT_SERVER_HEADLESS", "true")
    sys.path.insert(0, str(ROOT))
    from app import tower_html

    html = tower_html(
        [
            {
                "competitor": "Mercedes",
                "driver": "George Russell",
                "car_number": "63",
                "session_label": "Qualifying",
                "incident_summary": "Pit lane incident with Car 41",
                "penalty_kind": "reprimand",
            },
            {
                "competitor": "Ferrari",
                "driver": "Carlos Sainz",
                "car_number": "55",
                "session_label": "Race",
                "incident_summary": "Left the track and gained an advantage",
                "penalty_kind": "time_penalty",
            },
        ]
    )
    for line in html.splitlines():
        assert not re.match(r" {4,}", line), line
    assert html.count('class="row"') == 2
    assert "George Russell" in html
    assert "Carlos Sainz" in html


def test_file_is_filtered_without_dropping_rows():
    rows = load_decisions()
    assert len(rows) == 665
    competitive = [row for row in rows if is_competitive(row)]
    practice = [row for row in rows if row["session_type"] == "practice"]
    unknown = [row for row in rows if row["session_type"] == "unknown"]
    assert practice
    assert unknown
    assert len(competitive) + len(practice) + len(unknown) == len(rows)
    assert all(row["session_type"] in {"qualifying", "sprint_qualifying", "sprint", "race"} for row in competitive)
    shootout = [
        row
        for row in rows
        if "Sprint Shootout" in (row.get("document_title") or "")
    ]
    assert shootout
    assert all(row["session_type"] == "sprint_qualifying" for row in shootout)
    assert all(row["session_label"] == "Sprint Qualifying" for row in shootout)


def test_precedents_ignore_practice_in_the_stored_file():
    rows = load_decisions()
    practice_track = [
        row
        for row in rows
        if row["session_type"] == "practice" and row["incident_type"] == "track_limits"
    ]
    assert practice_track
    found = search_precedents(rows, "track_limits", penalty_kind="lap_deletion")
    assert found["similar_count"] > 0
    assert all(is_competitive(item) for item in found["examples"])
    assert all(item["id"] not in {row["id"] for row in practice_track} for item in found["examples"])


def test_timing_table_becomes_prose_from_a_stored_decision():
    rows = load_decisions()
    record = next(
        row
        for row in rows
        if row.get("document_title") == "Doc 40 - Infringement - Race Deleted Lap Times"
        and "Lance Stroll" in (row.get("incident_summary") or "")
    )
    text = explain_decision(record, use_llm=False)["explanation"]
    assert "Time of Day" not in text
    assert "Lap Time" not in text
    assert "1:51.654" not in text
    assert "Lance Stroll" in text
    assert "car 18" in text
    assert "Race" in text
    assert "turns" in text.lower()
    assert "Deletion of the lap times" in text
    assert "I don't know" in text


def test_app_imports_with_an_empty_pythonpath():
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env["STREAMLIT_SERVER_HEADLESS"] = "true"
    script = "import runpy; runpy.run_path('app.py', run_name='importing')"
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
