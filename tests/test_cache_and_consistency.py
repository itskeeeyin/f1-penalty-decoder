from f1_penalty_decoder.ingest import cache_filename
from f1_penalty_decoder.parse_decision import drop_shared_extracts, record_is_consistent


def test_cache_filename_uses_the_full_url():
    one = "https://www.fia.com/system/files/decision-document/2024_dutch_grand_prix_-_infringement_-_car_1.pdf"
    two = "https://www.fia.com/system/files/decision-document/2024_dutch_grand_prix_-_infringement_-_car_2.pdf"
    assert cache_filename(one) != cache_filename(two)
    assert cache_filename(one).endswith(".pdf")
    assert len(cache_filename(one)) > 40


def test_rejects_extract_about_a_different_car():
    ok, reason = record_is_consistent(
        {
            "document_title": "Infringement - Car 10 - Track limits",
            "incident_summary": "Car 44 left the track.",
            "offence_text": "",
            "reason": "",
            "penalty": "5 second time penalty.",
            "car_number": "44",
        }
    )
    assert ok is False
    assert "car" in reason


def test_keeps_a_matching_car():
    ok, _reason = record_is_consistent(
        {
            "document_title": "Offence - Car 63 - Unsafe release",
            "incident_summary": "Unsafe release.",
            "offence_text": "Breach of Article 34.14 a) of the FIA Formula One Sporting Regulations.",
            "reason": "Car 63 was released into the path of another car.",
            "penalty": "5 second time penalty.",
            "car_number": "63",
        }
    )
    assert ok is True


def test_drops_every_copy_of_a_shared_extract():
    shared = {
        "incident_summary": "Driver Assistants in Parc Ferme.",
        "penalty": "Fine of €10,000.",
        "offence_text": "Breach of Article 12.2.1 i) of the International Sporting Code.",
        "document_title": "",
        "reason": "",
        "car_number": "",
    }
    rows = [
        {**shared, "document_title": "Offence - Car 10 - Track Limits"},
        {**shared, "document_title": "Offence - Car 11 - Pit lane speeding"},
        {
            "document_title": "Offence - Car 63 - Unsafe release",
            "incident_summary": "Unsafe release.",
            "penalty": "5 second time penalty.",
            "offence_text": "Breach of Article 34.14 a).",
            "reason": "Car 63 was released unsafely.",
            "car_number": "63",
        },
    ]
    kept, dropped = drop_shared_extracts(rows)
    assert len(kept) == 1
    assert kept[0]["car_number"] == "63"
    assert len(dropped) == 2
