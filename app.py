"""Streamlit browser for stored stewards' decisions.

Run: streamlit run app.py
"""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path

_SRC = Path(__file__).resolve().parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import streamlit as st

from f1_penalty_decoder.explain import explain_decision, incident_preview
from f1_penalty_decoder.parse_decision import (
    parse_decision_text,
    session_label,
)
from f1_penalty_decoder.search import is_competitive, load_decisions, search_precedents

SESSION_FILTERS = (
    ("All competitive", ""),
    ("Qualifying", "qualifying"),
    ("Sprint Qualifying", "sprint_qualifying"),
    ("Sprint", "sprint"),
    ("Race", "race"),
)

st.set_page_config(
    page_title="Penalty decoder",
    page_icon="⏱",
    layout="wide",
    initial_sidebar_state="expanded",
)

TEAM_COLOURS = (
    ("ferrari", "#E8002D"),
    ("red bull", "#3671C6"),
    ("racing bulls", "#6C98FF"),
    ("rb ", "#6C98FF"),
    ("mercedes", "#27F4D2"),
    ("mclaren", "#FF8000"),
    ("aston martin", "#229971"),
    ("alpine", "#FF87BC"),
    ("williams", "#64C4FF"),
    ("haas", "#B6BABD"),
    ("sauber", "#52E252"),
    ("kick", "#52E252"),
    ("audi", "#F50537"),
    ("cadillac", "#C0C0C0"),
    ("alfa romeo", "#C92D4B"),
    ("alphatauri", "#5E8FAA"),
)


def team_colour(competitor: str) -> str:
    low = (competitor or "").lower()
    for needle, colour in TEAM_COLOURS:
        if needle in low:
            return colour
    return "#5c5c66"


def driver_code(name: str, number: str) -> str:
    parts = [part for part in (name or "").replace("-", " ").split() if part]
    if not parts:
        return (number or "—")[:3]
    surname = parts[-1]
    letters = "".join(ch for ch in surname.upper() if ch.isalpha())
    return (letters[:3] or (number or "—"))


def badge(kind: str) -> str:
    labels = {
        "time_penalty": "TIME",
        "grid": "GRID",
        "drive_through": "DT",
        "stop_go": "STOP/GO",
        "reprimand": "REP",
        "warning": "WARN",
        "fine": "FINE",
        "disqualification": "DSQ",
        "no_further_action": "NFA",
        "lap_deletion": "LAP",
        "points": "PTS",
        "other": "PEN",
        "unknown": "—",
    }
    return labels.get(kind, kind.upper()[:8] if kind else "—")


def inject_css() -> None:
    css = "\n".join(
        line.lstrip()
        for line in textwrap.dedent(
            """\
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Titillium+Web:wght@400;600;700&display=swap');
        html, body, [class*="css"] { font-family: "Titillium Web", "Arial Narrow", sans-serif; }
        .block-container { padding-top: 1.4rem; max-width: 1180px; }
        h1, h2, h3 {
            font-family: "Titillium Web", "Arial Narrow", sans-serif;
            font-weight: 700;
            letter-spacing: 0.04em;
            text-transform: uppercase;
        }
        .kicker {
            color: #E10600;
            font-weight: 700;
            letter-spacing: 0.18em;
            font-size: 0.78rem;
            margin-bottom: 0.2rem;
        }
        .disclaimer {
            color: #a1a1aa;
            font-size: 0.92rem;
            margin-bottom: 1.2rem;
        }
        .tower { display: flex; flex-direction: column; gap: 8px; margin: 0.6rem 0 1.2rem 0; }
        .row {
            display: grid;
            grid-template-columns: 8px 72px 1fr auto;
            gap: 14px;
            align-items: center;
            background: #141417;
            border-radius: 12px;
            padding: 12px 16px 12px 0;
            border: 1px solid #2a2a30;
        }
        .stripe { width: 8px; align-self: stretch; border-radius: 12px 0 0 12px; }
        .code { font-weight: 700; font-size: 1.35rem; letter-spacing: 0.06em; }
        .meta { color: #d4d4d8; font-size: 0.95rem; }
        .sub { color: #a1a1aa; font-size: 0.82rem; margin-top: 2px; }
        .badge {
            background: #E10600;
            color: white;
            font-weight: 700;
            letter-spacing: 0.08em;
            border-radius: 999px;
            padding: 6px 10px;
            font-size: 0.78rem;
        }
        .card {
            background: #141417;
            border: 1px solid #2a2a30;
            border-radius: 16px;
            padding: 18px 20px;
            margin-bottom: 14px;
        }
        .card h3 { margin-top: 0; }
        a { color: #ffb4b0; }
        </style>
        """
        ).splitlines()
    )
    st.markdown(css, unsafe_allow_html=True)


def row_html(item: dict, selected: bool) -> str:
    colour = team_colour(item.get("competitor") or "")
    outline = "outline: 1px solid #E10600;" if selected else ""
    summary = incident_preview(item.get("incident_summary") or item.get("document_title") or "")
    session = item.get("session_label") or item.get("session") or "Session not stated"
    # One line, no leading spaces. Streamlit markdown treats a 4-space indent as a code block,
    # so a joined multi-line row renders every row after the first as raw HTML.
    return (
        f'<div class="row" style="{outline}">'
        f'<div class="stripe" style="background:{colour}"></div>'
        f'<div class="code">{driver_code(item.get("driver") or "", item.get("car_number") or "")}</div>'
        f"<div>"
        f'<div class="meta">{item.get("driver") or "Driver not named in the extract"}'
        f' · #{item.get("car_number") or "—"} · {session}</div>'
        f'<div class="sub">{summary}</div>'
        f"</div>"
        f'<div class="badge">{badge(item.get("penalty_kind") or "")}</div>'
        f"</div>"
    )


def tower_html(items: list[dict]) -> str:
    rows = "".join(row_html(item, False) for item in items)
    return f'<div class="tower">{rows}</div>'


def main() -> None:
    _render()


def _render() -> None:
    inject_css()
    decisions = load_decisions()


    st.markdown('<div class="kicker">UNOFFICIAL FAN TOOL</div>', unsafe_allow_html=True)
    st.title("Penalty decoder")
    st.markdown(
        '<p class="disclaimer">Plain-English notes on public FIA Formula 1 stewards\' documents '
        "from 2022 onward. Not affiliated with the FIA or Formula 1. Not a substitute for the "
        "decision document or the Sporting Regulations.</p>",
        unsafe_allow_html=True,
    )

    if not decisions:
        st.error("No decisions file found. Run the ingest script described in the README.")
        st.stop()

    competitive = [item for item in decisions if is_competitive(item)]
    unknown_count = sum(1 for item in decisions if item.get("session_type") == "unknown")
    practice_count = sum(1 for item in decisions if item.get("session_type") == "practice")
    seasons = sorted({int(item["season"]) for item in competitive})
    with st.sidebar:
        st.header("Weekend")
        season = st.selectbox("Season", seasons, index=len(seasons) - 1)
        events = sorted({item["event"] for item in competitive if int(item["season"]) == int(season)})
        event = st.selectbox("Grand Prix", events)
        session_choice = st.selectbox(
            "Session",
            [label for label, _key in SESSION_FILTERS],
        )
        session_key = dict(SESSION_FILTERS)[session_choice]
        kinds = ["All types"] + sorted({item["incident_type"] for item in competitive})
        kind = st.selectbox("Incident type", kinds)
        st.caption(
            f"{len(competitive)} competitive decisions in the local file "
            "(Qualifying, Sprint Qualifying, Sprint, and Race). "
            f"{unknown_count} decisions with an unknown session are excluded from this view. "
            f"{practice_count} practice-session decisions stay in the file and are not listed. "
            "Precedent counts use competitive-session decisions only."
        )

    pool = [
        item
        for item in competitive
        if int(item["season"]) == int(season) and item["event"] == event
    ]
    if session_key:
        pool = [item for item in pool if item.get("session_type") == session_key]
    if kind != "All types":
        pool = [item for item in pool if item["incident_type"] == kind]

    st.subheader(f"{event} · {season}")
    labels = [
        f"{item.get('car_number') or '—'} {item.get('driver') or item['document_title'][:48]}"
        for item in pool
    ]
    if not pool:
        st.info("No stored decision for this filter.")
        choice = None
    else:
        st.markdown(tower_html(pool[:40]), unsafe_allow_html=True)
        if len(pool) > 40:
            st.caption(f"Showing the first 40 of {len(pool)} rows. Use the picker for the rest.")
        index = st.selectbox("Decision", range(len(pool)), format_func=lambda i: labels[i])
        choice = pool[index]

    st.divider()
    paste = st.text_area(
        "Or paste a decision",
        height=140,
        placeholder="Paste the text of a stewards' document. The note below uses only that text and the stored regulation file.",
    )

    if paste.strip():
        parsed = parse_decision_text(paste)
        record = {
            "id": "pasted",
            "season": int(season),
            "event": event,
            "session": parsed["session"],
            "session_type": parsed.get("session_type") or "",
            "session_label": session_label(parsed.get("session_type") or ""),
            "driver": parsed["driver"],
            "car_number": parsed["car_number"],
            "incident_summary": parsed["incident_summary"],
            "incident_type": parsed["incident_type"],
            "article": parsed["article"],
            "penalty": parsed["penalty"],
            "penalty_kind": parsed["penalty_kind"],
            "reason": parsed["reason"],
            "document_url": "",
            "document_title": "Pasted text",
        }
        st.caption("This view uses the pasted text, checked against the regulation file for the season selected in the sidebar.")
    else:
        record = choice

    if record:
        left, right = st.columns([1.35, 1])
        with left:
            st.markdown('<div class="card">', unsafe_allow_html=True)
            st.markdown("### What the document says")
            explained = explain_decision(record, use_llm=None)
            st.write(explained["explanation"])
            if explained["source"] == "deterministic":
                st.caption("Written from the document fields and the stored regulation excerpt. No model key is in use.")
            else:
                st.caption("Drafted by the configured model from those same fields. The source document is still the record.")
            rule = explained.get("regulation")
            if rule and rule.get("source_url"):
                st.markdown(f"Regulation file: [{rule.get('issue') or rule.get('title')}]({rule['source_url']})")
            elif record.get("article"):
                st.markdown("**I don't know** the matching article text in the stored regulation file.")
            st.markdown("</div>", unsafe_allow_html=True)
        with right:
            st.markdown('<div class="card">', unsafe_allow_html=True)
            st.markdown("### Has this happened before?")
            found = search_precedents(
                decisions,
                record.get("incident_type") or "",
                penalty_kind=record.get("penalty_kind") or "",
                exclude_id=record.get("id") or "",
            )
            if found["similar_count"] == 0:
                st.write("No other stored decision carries this incident type, so there is no count to show.")
            else:
                st.write(
                    f"{found['similar_count']} other stored competitive-session decisions are tagged "
                    f"{found['incident_type'].replace('_', ' ')}."
                )
                if found["penalty_kind"] and found["penalty_kind"] != "unknown":
                    st.write(
                        f"{found['same_penalty_count']} of those {found['similar_count']} have the same penalty tag ({found['penalty_kind'].replace('_', ' ')})."
                    )
                breakdown = found["penalty_breakdown"]
                if breakdown:
                    st.write(
                        "Penalty tags in that set: "
                        + ", ".join(f"{name} {count}" for name, count in sorted(breakdown.items()))
                        + "."
                    )
            for example in found["examples"][:5]:
                st.markdown(
                    f"- {example.get('season')} {example.get('event')}: "
                    f"{example.get('driver') or 'car ' + str(example.get('car_number') or '')} — "
                    f"{example.get('penalty') or 'penalty text not parsed'} "
                    f"([document]({example.get('document_url')}))"
                )
            st.markdown("</div>", unsafe_allow_html=True)
            if record.get("document_url"):
                st.markdown(
                    f"**Source document:** [{record.get('document_title')}]({record['document_url']})"
                )
            if record.get("article"):
                st.markdown(f"**Article cited in the document:** {record['article']}")

if __name__ == "__main__":
    main()
