from f1_penalty_decoder.explain import explain_decision
from f1_penalty_decoder.regulations import lookup_article
from f1_penalty_decoder.search import search_precedents

CORPUS = [
    {"id": "a", "incident_type": "impeding", "penalty_kind": "grid", "event": "A", "season": 2025, "driver": "A", "car_number": "1", "penalty": "3 grid", "document_url": "https://example.test/a", "document_title": "A"},
    {"id": "b", "incident_type": "impeding", "penalty_kind": "grid", "event": "B", "season": 2025, "driver": "B", "car_number": "2", "penalty": "3 grid", "document_url": "https://example.test/b", "document_title": "B"},
    {"id": "c", "incident_type": "impeding", "penalty_kind": "reprimand", "event": "C", "season": 2024, "driver": "C", "car_number": "3", "penalty": "reprimand", "document_url": "https://example.test/c", "document_title": "C"},
    {"id": "d", "incident_type": "unsafe_release", "penalty_kind": "time_penalty", "event": "D", "season": 2024, "driver": "D", "car_number": "4", "penalty": "5 seconds", "document_url": "https://example.test/d", "document_title": "D"},
]


def test_precedent_counts_match_rows():
    result = search_precedents(CORPUS, "impeding", penalty_kind="grid", exclude_id="a")
    assert result["similar_count"] == 2
    assert result["same_penalty_count"] == 1
    assert result["penalty_breakdown"]["grid"] == 1
    assert result["penalty_breakdown"]["reprimand"] == 1


def test_other_type_does_not_invent_matches():
    result = search_precedents(CORPUS, "other", penalty_kind="time_penalty")
    assert result["similar_count"] == 0
    assert result["examples"] == []


def test_explain_unknown_rule_without_article():
    text = explain_decision(
        {"season": 2025, "incident_summary": "Car 1 left the track.", "penalty": "5 second time penalty.", "article": "", "session": "Race"},
        use_llm=False,
    )
    assert text["source"] == "deterministic"
    assert "I don't know" in text["explanation"]
    assert text["rule_found"] is False


def test_explain_quotes_stored_article_when_present():
    found = lookup_article(2024, "33.3")
    assert found is not None
    assert "track" in found["text"].lower()
    text = explain_decision(
        {
            "season": 2024,
            "incident_summary": "Car 1 left the track and gained an advantage.",
            "penalty": "5 second time penalty.",
            "article": "33.3",
            "session": "Race",
            "reason": "The driver left the track.",
        },
        use_llm=False,
    )
    assert text["rule_found"] is True
    assert "33.3" in text["explanation"]
    assert "2024" in text["explanation"]
    assert "I don't know" not in text["explanation"]
