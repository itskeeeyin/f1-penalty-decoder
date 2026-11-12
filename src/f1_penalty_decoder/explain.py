"""Plain-English explanations grounded in a decision and a regulation excerpt."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

from f1_penalty_decoder.regulations import lookup_article

UNKNOWN = "I don't know"


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
    where = f" It applies to the {session}." if session else ""
    return f"The stewards' decision, in their words, is: {penalty}{where}"


def explain_decision(record: dict, *, use_llm: bool | None = None) -> dict:
    """Explain one stored decision or a parsed paste.

    The deterministic text is always available. An LLM is used only when an
    API key is set and ``use_llm`` is not False. The model is given only the
    document fields and the regulation excerpt.
    """
    year = int(record.get("season") or 0)
    article = record.get("article") or ""
    rule_text, rule = _rule_sentence(year, article)
    what = record.get("incident_summary") or ""
    if what:
        happened = f"The document describes the incident as: {what}"
    else:
        happened = f"{UNKNOWN} what happened. This record has no incident summary from the document."
    penalty = _penalty_sentence(record.get("penalty") or "", record.get("session") or "")
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
