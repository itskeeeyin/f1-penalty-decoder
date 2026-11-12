"""Plain-English explanations grounded in a decision and a regulation excerpt."""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request

from f1_penalty_decoder.regulations import lookup_article

UNKNOWN = "I don't know"

_TABLE_HEADER = re.compile(
    r"(?:No\.?\s+)?(?:Turn\s+)?Car\s+Driver\s+Competitor\s+Time\s+of\s+Day(?:\s+Lap(?:\s+Time)?)?",
    flags=re.IGNORECASE,
)
_DRIVER = r"[A-Z][A-Za-z']+(?:\s+(?:de|da|di|van|von|le))?\s+[A-Z][A-Za-z']+"
_ROW_TURN = re.compile(rf"(?:^|\s)(\d{{1,3}})\s+(\d{{1,2}})\s+(\d{{1,2}})\s+({_DRIVER})(?=\s)")
_ROW_NOTURN = re.compile(rf"(?:^|\s)(\d{{1,3}})\s+(\d{{1,2}})\s+({_DRIVER})(?=\s)")
_TURNS = re.compile(
    r"turns?\s+((?:\d{1,2}\s*(?:,|and)?\s*)+)",
    flags=re.IGNORECASE,
)


def _timing_rows(table: str, has_turn: bool) -> list[dict]:
    pattern = _ROW_TURN if has_turn else _ROW_NOTURN
    rows = []
    for match in pattern.finditer(table):
        if has_turn:
            index, turn, car, driver = match.groups()
        else:
            index, car, driver = match.groups()
            turn = ""
        rows.append({"index": int(index), "turn": turn, "car": car, "driver": driver})
    return rows


def _turn_phrase(prose: str, rows: list[dict]) -> str:
    match = _TURNS.search(prose)
    if match:
        numbers = re.findall(r"\d{1,2}", match.group(1))
        if numbers:
            return "turns " + _and_list(numbers)
    turns = []
    for row in rows:
        if row["turn"] and row["turn"] not in turns:
            turns.append(row["turn"])
    if not turns:
        return ""
    if len(turns) == 1:
        return "turn " + turns[0]
    return "turns " + _and_list(turns)


def _and_list(items: list[str]) -> str:
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return f"{items[0]} and {items[1]}"
    return ", ".join(items[:-1]) + " and " + items[-1]


def _car_phrase(rows: list[dict]) -> str:
    seen: list[str] = []
    labels: list[str] = []
    for row in rows:
        key = row["car"] + "|" + row["driver"]
        if key in seen:
            continue
        seen.append(key)
        labels.append(f"car {row['car']} ({row['driver']})")
    if not labels:
        return ""
    shown = labels[:8]
    phrase = _and_list(shown)
    extra = len(labels) - len(shown)
    if extra:
        phrase += f" and {extra} more"
    return phrase


def summarise_timing_table(record: dict) -> str:
    """Plain-English note for a deleted-lap or timing-table document.

    The stored incident line pastes the extracted table. This keeps the
    sentence in front of the header and names the cars, without the row times.
    """
    summary = record.get("incident_summary") or ""
    match = _TABLE_HEADER.search(summary)
    if not match:
        return ""
    prose = re.sub(r"\s+", " ", summary[: match.start()]).strip(" .")
    prose = re.sub(r"^the (?:f1 )?cars? below\s+", "cars ", prose, flags=re.IGNORECASE)
    prose = re.sub(r"^the f1 cars\s+", "cars ", prose, flags=re.IGNORECASE)
    has_turn = bool(re.search(r"\bTurn\b", match.group(0), flags=re.IGNORECASE))
    rows = _timing_rows(summary[match.end() :], has_turn)
    session = record.get("session_label") or record.get("session") or ""
    where = f"In {session}, " if session else ""
    if prose:
        sentence = f"{where}{prose[0].lower()}{prose[1:]}."
    else:
        sentence = f"{where}the document lists cars in a timing table."
    if not where:
        sentence = sentence[0].upper() + sentence[1:]
    turns = _turn_phrase(prose, rows)
    if turns and turns.lower() not in sentence.lower():
        sentence = sentence[:-1] + f" at {turns}."
    cars = _car_phrase(rows)
    if cars:
        sentence += f" Cars named in the stored extract: {cars}."
    else:
        sentence += f" {UNKNOWN} which cars are in the timing table."
    partial = (
        not rows
        or rows[0]["index"] != 1
        or len(summary) >= 490
    )
    if partial:
        sentence += (
            f" {UNKNOWN} whether the document lists further rows; "
            "the stored extract does not include the whole table."
        )
    return sentence


def _decision_line(penalty: str) -> str:
    text = (penalty or "").strip()
    if not text:
        return ""
    if _TABLE_HEADER.search(text) or ("Enclosed" in text and "Description" in text):
        return ""
    return text


def incident_preview(summary: str, limit: int = 110) -> str:
    """Short list-row line. Timing-table headers are left out."""
    text = summary or ""
    match = _TABLE_HEADER.search(text)
    if match:
        text = text[: match.start()]
    text = re.sub(r"\s+", " ", text).strip(" .")
    return text[:limit]


def describe_incident(record: dict) -> str:
    summary = record.get("incident_summary") or ""
    if _TABLE_HEADER.search(summary):
        return summarise_timing_table(record)
    if summary:
        return f"The document describes the incident as: {summary}"
    return f"{UNKNOWN} what happened. This record has no incident summary from the document."


def _rule_sentence(year: int, article: str) -> tuple[str, dict | None]:
    if not article:
        return (
            f"{UNKNOWN} which Sporting Regulations article this document cites.",
            None,
        )
    found = lookup_article(year, article)
    if not found or not found.get("text"):
        return (
            f"The document cites Article {article}. {UNKNOWN} the wording of that "
            f"article in the {year} Sporting Regulations file stored with this tool.",
            None,
        )
    version = found.get("issue") or found.get("regulation") or f"{year} Sporting Regulations"
    return (
        f"Article {found['article']} of the {year} FIA Formula One Sporting Regulations "
        f"({version}) says: {found['text']}",
        found,
    )


def _penalty_sentence(penalty: str, session: str) -> str:
    if not penalty:
        return f"{UNKNOWN} what the stewards decided. The parsed document has no Decision line."
    text = penalty.rstrip()
    if text[-1] not in ".!?":
        text += "."
    where = f" It applies to the {session}." if session else ""
    return f"The stewards' decision, in their words, is: {text}{where}"


def explain_decision(record: dict, *, use_llm: bool | None = None) -> dict:
    """Explain one stored decision or a parsed paste.

    The deterministic text is always available. An LLM is used only when an
    API key is set and ``use_llm`` is not False. The model is given only the
    document fields and the regulation excerpt.
    """
    year = int(record.get("season") or 0)
    article = record.get("article") or ""
    rule_text, rule = _rule_sentence(year, article)
    happened = describe_incident(record)
    session = record.get("session_label") or record.get("session") or ""
    penalty = _penalty_sentence(_decision_line(record.get("penalty") or ""), session)
    reason = record.get("reason") or ""
    reason_bit = (
        f" The stewards' stated reason includes: {reason}"
        if reason
        else ""
    )
    fallback = " ".join([happened, rule_text, penalty + reason_bit])
    source = "deterministic"
    text = fallback
    if use_llm is not False:
        generated = _maybe_llm(record, rule, fallback)
        if generated:
            text = generated
            source = "llm"
    return {
        "explanation": text,
        "source": source,
        "article": article,
        "regulation": None
        if rule is None
        else {
            "title": rule.get("regulation"),
            "issue": rule.get("issue"),
            "source_url": rule.get("source_url"),
            "article": rule.get("article"),
            "cited_as": rule.get("cited_as") or article,
        },
        "rule_found": rule is not None,
    }


def _maybe_llm(record: dict, rule: dict | None, fallback: str) -> str | None:
    xai = os.environ.get("XAI_API_KEY", "").strip()
    gemini = os.environ.get("GEMINI_API_KEY", "").strip()
    if not xai and not gemini:
        return None
    payload = {
        "incident_summary": record.get("incident_summary") or "",
        "penalty": record.get("penalty") or "",
        "reason": record.get("reason") or "",
        "article": record.get("article") or "",
        "season": record.get("season"),
        "session": record.get("session") or "",
        "regulation_excerpt": None if rule is None else rule.get("text"),
        "regulation_source": None if rule is None else rule.get("source_url"),
    }
    instruction = (
        "Explain this Formula 1 stewards' decision in plain English for a fan. "
        "Use only the JSON fields. If regulation_excerpt is null, write exactly "
        "\"I don't know\" for the rule wording. Do not invent similar cases, "
        "quotes, or article text. Three short paragraphs: what happened, the rule, "
        "what the penalty means."
    )
    try:
        if xai:
            return _xai(xai, instruction, payload)
        return _gemini(gemini, instruction, payload)
    except Exception:
        return fallback


def _xai(key: str, instruction: str, payload: dict) -> str:
    body = json.dumps(
        {
            "model": os.environ.get("XAI_MODEL", "grok-4-fast-non-reasoning"),
            "temperature": 0,
            "messages": [
                {"role": "system", "content": instruction},
                {"role": "user", "content": json.dumps(payload)},
            ],
        }
    ).encode()
    request = urllib.request.Request(
        "https://api.x.ai/v1/chat/completions",
        data=body,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        data = json.loads(response.read().decode())
    return data["choices"][0]["message"]["content"].strip()


def _gemini(key: str, instruction: str, payload: dict) -> str:
    model = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent?key={key}"
    )
    body = json.dumps(
        {
            "contents": [
                {
                    "parts": [
                        {"text": instruction + "\n\n" + json.dumps(payload)}
                    ]
                }
            ],
            "generationConfig": {"temperature": 0},
        }
    ).encode()
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        data = json.loads(response.read().decode())
    return data["candidates"][0]["content"]["parts"][0]["text"].strip()
