"""Parse stewards' decision text into structured fields.

The parser only copies spans that appear in the document. Missing fields stay
empty so callers can say they do not know, instead of filling gaps.
"""

from __future__ import annotations

import re
from typing import Any

NBSP = "\u00a0"

INCIDENT_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("unsafe_release", ("unsafe release", "released in an unsafe")),
    ("causing_a_collision", ("causing a collision", "caused a collision")),
    ("impeding", ("imped",)),
    ("track_limits", (
        "leaving the track",
        "track limits",
        "not using the track",
        "deleted lap",
    )),
    ("pit_lane_speeding", ("pit lane speeding", "speeding in the pit")),
    ("unsafe_rejoin", ("rejoin", "re-join")),
    ("yellow_flags", ("yellow flag", "double yellow", "yellow flags")),
    ("false_start", ("false start",)),
    ("weaving", ("more than one change of direction", "weaving")),
    ("parc_ferme", ("parc ferm", "parc fermé")),
    ("formation_lap", ("formation lap", "practice start")),
]

PENALTY_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("no_further_action", ("no further action", "no penalty", "protest is rejected", "not founded")),
    ("disqualification", ("disqualif",)),
    ("drive_through", ("drive through", "drive-through")),
    ("stop_go", ("stop and go", "stop-go", "stop/go")),
    ("grid", ("grid position", "grid drop", "drop of")),
    ("time_penalty", ("time penalty", "second penalty", "seconds penalty")),
    ("reprimand", ("reprimand",)),
    ("warning", ("warning",)),
    ("fine", ("fine of", " fined", "€", "euro")),
    ("lap_deletion", ("lap time", "deleted")),
    ("points", ("penalty point", "penalty points")),
]


def clean_text(text: str) -> str:
    text = text.replace(NBSP, " ").replace("\u200b", "")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _field(text: str, labels: tuple[str, ...], stops: tuple[str, ...]) -> str:
    label = "|".join(re.escape(item) for item in labels)
    stop = "|".join(re.escape(item) for item in stops)
    match = re.search(
        rf"(?:{label})\s*(.+?)(?=\n\s*(?:{stop})\b|\Z)",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not match:
        return ""
    value = re.sub(r"\s+", " ", match.group(1)).strip(" :-")
    return value


_ARTICLE = re.compile(
    r"Article\s+([A-Za-z]?\d+(?:\.\d+)*)(?:\s*\(?\s*([a-z])\s*\)?(?![a-z]))?",
    flags=re.IGNORECASE,
)


def extract_article(text: str) -> str:
    """Prefer the article attached to the Formula 1 regulations, not the Code."""
    matches = list(_ARTICLE.finditer(text))
    if not matches:
        return ""
    for match in matches:
        window = text[match.end(): match.end() + 90].lower()
        if "sporting regulation" in window or "f1 regulation" in window or "formula one" in window:
            return _article_from_match(match)
    return _article_from_match(matches[0])


def _article_from_match(match: re.Match) -> str:
    suffix = match.group(2) or ""
    return _normalise_article(match.group(1) + suffix)


def _normalise_article(raw: str) -> str:
    return re.sub(r"[^a-z0-9.]", "", re.sub(r"\s+", "", raw).lower())


def classify_incident(*parts: str) -> str:
    blob = " ".join(parts).lower()
    for name, needles in INCIDENT_RULES:
        if any(needle in blob for needle in needles):
            return name
    return "other"


def classify_penalty(decision: str) -> str:
    blob = decision.lower()
    if not blob.strip():
        return "unknown"
    # A time penalty can sit next to penalty points. Prefer the sporting penalty.
    for name, needles in PENALTY_RULES:
        if name == "points":
            continue
        if any(needle in blob for needle in needles):
            return name
    if any(needle in blob for needle in PENALTY_RULES[-1][1]):
        return "points"
    return "other"


def car_number_from(*parts: str) -> str:
    blob = " ".join(parts)
    match = re.search(r"\bCar\s+(\d{1,3})\b", blob, flags=re.IGNORECASE)
    if match:
        return match.group(1)
    match = re.search(r"No\s*/\s*Driver\s+(\d{1,3})\b", blob, flags=re.IGNORECASE)
    if match:
        return match.group(1)
    return ""


def driver_name(text: str) -> str:
    match = re.search(
        r"No\s*/\s*Driver\s+\d{1,3}\s*[-–]\s*([A-Z][A-Za-z' .\-]+)",
        text,
    )
    if not match:
        return ""
    name = match.group(1).strip()
    name = re.split(r"\s{2,}|Competitor|Time\b|Session\b", name)[0].strip()
    return name


COMPETITIVE_SESSION_TYPES = ("qualifying", "sprint_qualifying", "sprint", "race")

SESSION_LABELS = {
    "qualifying": "Qualifying",
    "sprint_qualifying": "Sprint Qualifying",
    "sprint": "Sprint",
    "race": "Race",
    "practice": "Practice",
}


def classify_session(text: str) -> str:
    """Map a session string onto a session type.

    Practice labels (``Free Practice 1``, ``Practice 2``, ``FP3``) collapse to
    ``practice``. ``Sprint Shootout`` is the old name for Sprint Qualifying.
    Anything else, including an empty string, is ``unknown``.
    """
    low = re.sub(r"\s+", " ", (text or "").lower()).strip()
    if not low:
        return "unknown"
    if "sprint shootout" in low or "sprint qualifying" in low:
        return "sprint_qualifying"
    if (
        re.search(r"\bfp\s*[123]\b", low)
        or "free practice" in low
        or re.search(r"\bpractice(?:\s*[123])?\b", low)
    ):
        return "practice"
    if re.search(r"\bsprint\b", low):
        return "sprint"
    if "qualifying" in low:
        return "qualifying"
    if re.search(r"\brace\b", low):
        return "race"
    return "unknown"


def session_type_for_record(record: dict[str, Any]) -> str:
    """Classify a stored row from its session line, then its title.

    A session line of ``Sprint`` is Sprint Qualifying when the document title
    says Sprint Shootout or Sprint Qualifying. The stored session string is
    left unchanged.
    """
    primary = classify_session(record.get("session") or "")
    title = classify_session(record.get("document_title") or "")
    if primary == "sprint" and title == "sprint_qualifying":
        return "sprint_qualifying"
    if primary == "unknown":
        return title
    return primary


def session_label(session_type: str) -> str:
    return SESSION_LABELS.get(session_type, "")


def session_name(text: str, title: str) -> str:
    found = _field(
        text,
        ("Session",),
        ("Fact", "Offence", "Infringement", "Decision", "Reason", "Competitor"),
    )
    kind = classify_session(found) if found else "unknown"
    if kind == "unknown":
        kind = classify_session(title)
    return session_label(kind)


def cited_cars(text: str) -> set[str]:
    return set(re.findall(r"\bcar\s+(\d{1,3})\b", text or "", flags=re.IGNORECASE))


def record_is_consistent(record: dict[str, Any]) -> tuple[bool, str]:
    """Reject an extract that cannot belong to its document title.

    A shared cache file previously copied one PDF's text onto many titles.
    Those rows repeat the same extract, or name a car the title does not.
    """
    title = record.get("document_title") or ""
    body = " ".join(
        [
            record.get("incident_summary") or "",
            record.get("offence_text") or "",
            record.get("reason") or "",
            record.get("penalty") or "",
        ]
    )
    title_cars = cited_cars(title)
    body_cars = cited_cars(body)
    number = str(record.get("car_number") or "")
    if number and title_cars and number not in title_cars:
        return False, "parsed car number is not the car in the document title"
    if title_cars and body_cars and title_cars.isdisjoint(body_cars):
        return False, "car number in the title does not appear in the extract"
    return True, ""


def drop_shared_extracts(records: list[dict[str, Any]]) -> tuple[list[dict], list[dict]]:
    """Drop every row that shares an identical extract with a different title."""
    groups: dict[tuple, list[int]] = {}
    for index, record in enumerate(records):
        key = (
            record.get("incident_summary") or "",
            record.get("penalty") or "",
            record.get("offence_text") or "",
        )
        groups.setdefault(key, []).append(index)
    shared = {index for indexes in groups.values() if len(indexes) > 1 for index in indexes}
    kept = []
    dropped = []
    for index, record in enumerate(records):
        if index in shared:
            dropped.append({**record, "status": "dropped", "error": "identical extract used for more than one document title"})
            continue
        ok, reason = record_is_consistent(record)
        if not ok:
            dropped.append({**record, "status": "dropped", "error": reason})
            continue
        kept.append(record)
    return kept, dropped


def parse_decision_text(text: str, title: str = "") -> dict[str, Any]:
    """Return fields copied from decision text. Empty string means not found."""
    cleaned = clean_text(text)
    stops = (
        "Fact",
        "Offence",
        "Offense",
        "Infringement",
        "Decision",
        "Reason",
        "Competitors are reminded",
        "The Stewards",
    )
    fact = _field(cleaned, ("Fact",), stops)
    offence = _field(cleaned, ("Offence", "Offense", "Infringement"), stops)
    decision = _field(cleaned, ("Decision",), stops)
    reason = _field(
        cleaned,
        ("Reason",),
        ("Competitors are reminded", "The Stewards", "Decisions of the Stewards"),
    )
    article = extract_article(offence or cleaned)
    number = car_number_from(title, cleaned)
    incident = classify_incident(title, fact, offence)
    penalty_kind = classify_penalty(decision)
    summary = fact or title
    return {
        "car_number": number,
        "driver": driver_name(cleaned),
        "competitor": _field(cleaned, ("Competitor",), ("Time", "Session", "Fact", "Offence", "Infringement")),
        "session": session_name(cleaned, title),
        "session_type": classify_session(session_name(cleaned, title)),
        "incident_summary": summary[:500],
        "offence_text": offence[:500],
        "article": article,
        "penalty": decision[:400],
        "penalty_kind": penalty_kind,
        "incident_type": incident,
        "reason": reason[:1500],
    }
