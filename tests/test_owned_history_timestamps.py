from peaks.adapters.riot.owned_history import history_details


def parsed(**times):
    return history_details({"games": [{"json": {"gameId": 42, "platformId": "EUW1",
                                                "participants": [{"puuid": "owner"}], **times}}]},
                           puuid="owner", game="TFT")[0][2]


def test_native_tft_creation_precedes_later_publication_time():
    assert parsed(gameCreation=1_789_880_000_000, game_datetime="1789882200000") == 1_789_880_000


def test_explicit_start_wins_and_bad_start_falls_back_to_creation():
    assert parsed(gameStartTimestamp=1_789_880_001_000, gameCreation=1_789_880_000_000) == 1_789_880_001
    assert parsed(gameStartTimestamp=None, gameCreation=1_789_880_000_000) == 1_789_880_000
    assert parsed(gameStartTimestamp=True, gameCreation=1_789_880_000_000) == 1_789_880_000


def test_api_payload_with_only_game_datetime_keeps_its_timestamp():
    assert parsed(game_datetime="1789880000000") == 1_789_880_000
    assert parsed(game_datetime=float("nan")) is None
