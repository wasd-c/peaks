"""A recorded composition must retain its original set through presentation."""
from peaks.adapters.riot.tft_composition import composition_view
from peaks.application.runtime import RiotSearchService


def test_set_context_survives_provider_and_saved_dtos():
    raw = {"tft_set_number": 10, "tft_set_core_name": "TFTSet10",
           "units": [{"character_id": "TFT10_Ahri", "tier": 2}]}
    view = composition_view(raw)
    assert view == {"setNumber": 10, "setVariant": "TFTSet10", "units": [{"id": "TFT10_Ahri", "stars": 2}]}
    assert composition_view(view) == view


def test_set_context_is_bounded_and_does_not_leak_arbitrary_fields():
    assert composition_view({"setNumber": True, "setVariant": "../secret", "token": "private"}) == {}
    assert composition_view({"setNumber": 1001, "setVariant": 17}) == {}


def test_public_match_teams_carry_recorded_set():
    teams = RiotSearchService._public_match_teams("TFT", [{"puuid": "owned", "placement": 1,
        "units": [{"character_id": "TFT10_Ahri", "tier": 2}]}], puuid="owned", set_number=10, set_variant="TFTSet10")
    composition = teams[0]["players"][0]["composition"]
    assert composition["setNumber"] == 10
    assert composition["setVariant"] == "TFTSet10"
