from f1_penalty_decoder.parse_decision import classify_incident, parse_decision_text

RUSSELL = """
No / Driver 63 - George Russell
Competitor Mercedes-AMG Petronas F1 Team
Time 17:26
Session Race
Fact Unsafe release.
Offence Breach of Article 34.14 a) of the FIA Formula One Sporting Regulations.
Decision 5 second time penalty.
Reason The Stewards reviewed multiple angles of video evidence. Car 63 was released from
the pit stop position into the path of NOR who had to take evasive action.
"""

SAINZ = """
No / Driver 55 - Carlos Sainz
Competitor Atlassian Williams Racing
Session Qualifying
Fact Car 55 unnecessarily impeded Car 44 in turn 1.
Infringement Breach of Article 37.5 of the FIA Formula One Sporting Regulations.
Decision Drop of 3 grid positions for the next Race in which the driver participates.
Reason The Stewards heard from the driver of Car 55.
"""


def test_unsafe_release_fields():
    parsed = parse_decision_text(RUSSELL, "Offence - Car 63 - Unsafe release")
    assert parsed["car_number"] == "63"
    assert parsed["driver"] == "George Russell"
    assert parsed["session"] == "Race"
    assert parsed["article"] == "34.14a"
    assert parsed["penalty_kind"] == "time_penalty"
    assert parsed["incident_type"] == "unsafe_release"
    assert "Unsafe release" in parsed["incident_summary"]


def test_impeding_fields():
    parsed = parse_decision_text(SAINZ, "Infringement - Car 55 - Impeding")
    assert parsed["article"] == "37.5"
    assert parsed["penalty_kind"] == "grid"
    assert parsed["incident_type"] == "impeding"
    assert parsed["session"] == "Qualifying"


def test_session_labels_collapse_practice_and_shootout():
    practice = parse_decision_text(
        "No / Driver 63 - George Russell\nSession Free Practice 1\nFact Car 63 left the track.\nDecision No further action.",
        "Practice 1",
    )
    assert practice["session"] == "Practice"
    assert practice["session_type"] == "practice"
    shootout = parse_decision_text(
        "Session Sprint Shootout\nFact The cars below exceeded the time limit.\nDecision No further action.",
        "Decision - Sprint Shootout",
    )
    assert shootout["session"] == "Sprint Qualifying"
    assert shootout["session_type"] == "sprint_qualifying"
    fp3 = parse_decision_text("Session FP3\nFact Noted.\nDecision Warning.", "FP3")
    assert fp3["session"] == "Practice"
    assert fp3["session_type"] == "practice"


def test_missing_article_stays_blank():
    parsed = parse_decision_text("Fact Something happened.\nDecision No further action.", "Decision")
    assert parsed["article"] == ""
    assert parsed["penalty_kind"] == "no_further_action"


def test_classify_track_limits():
    assert classify_incident("Leaving the track and gaining an advantage") == "track_limits"


def test_article_does_not_swallow_the_word_of():
    from f1_penalty_decoder.parse_decision import extract_article
    assert extract_article("Breach of Article 34.7 of the FIA Formula One Sporting Regulations.") == "34.7"
    assert extract_article("Breach of Article 34.14 a) of the FIA Formula One Sporting Regulations.") == "34.14a"
    assert extract_article("Breach of Article B1.6.2a of the FIA F1 Regulations.") == "b1.6.2a"
