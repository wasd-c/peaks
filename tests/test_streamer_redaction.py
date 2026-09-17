from __future__ import annotations

from peaks.adapters.riot.redaction import redact_match_payload, redact_player


def test_incognito_identity_is_removed_without_stable_alias() -> None:
    payload = {
        "Players": [
            {
                "Subject": "secret-puuid",
                "GameName": "Hidden Name",
                "TagLine": "1234",
                "PlayerIdentity": {"Subject": "secret-puuid", "Incognito": True},
                "Incognito": True,
                "Rank": 24,
            }
        ]
    }
    redacted = redact_match_payload(payload)
    player = redacted["Players"][0]
    assert player["Subject"] is None
    assert player["GameName"] is None
    assert player["TagLine"] is None
    assert player["PlayerIdentity"].get("Subject") is None
    assert "secret-puuid" not in repr(redacted)
    assert player["display_name"] == "Anonymous player"
    assert player["Rank"] == 24
    assert payload["Players"][0]["Subject"] == "secret-puuid"


def test_streamer_mode_redacts_other_players_but_can_preserve_marked_self() -> None:
    own = {"name": "Me", "isSelf": True}
    other = {"name": "Opponent", "puuid": "p-2"}
    assert redact_player(own, streamer_mode=True)["name"] == "Me"
    result = redact_player(other, streamer_mode=True)
    assert result["name"] is None
    assert result["puuid"] is None
    assert "Opponent" not in repr(result)


def test_unknown_privacy_marker_fails_closed_even_when_value_looks_false() -> None:
    result = redact_player(
        {"name": "Opponent", "privacyMode": "false", "isSelf": True},
        is_self=True,
    )
    assert result["name"] is None
    assert result["redacted"] is True
    assert "Opponent" not in repr(result)


def test_non_boolean_known_privacy_marker_fails_closed() -> None:
    result = redact_player({"name": "Opponent", "Incognito": "false"})
    assert result["name"] is None
    assert result["redacted"] is True


def test_malformed_self_marker_cannot_bypass_streamer_redaction() -> None:
    result = redact_player(
        {"name": "Opponent", "isSelf": "false"},
        streamer_mode=True,
    )
    assert result["name"] is None
    assert "Opponent" not in repr(result)


def test_redaction_does_not_deanonymize_from_nested_records() -> None:
    result = redact_match_payload(
        {
            "participants": [
                {"summonerName": "Nope", "summonerId": "id", "isSelf": False},
                {"summonerName": "Mine", "isSelf": True},
            ]
        },
        streamer_mode=True,
    )
    assert result["participants"][0]["summonerName"] is None
    assert result["participants"][0]["summonerId"] is None
    assert result["participants"][1]["summonerName"] == "Mine"  # explicitly marked local player
