from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path


def load_projector():
    path = Path(__file__).parents[1] / "scripts" / "riot_event_projection.py"
    spec = importlib.util.spec_from_file_location("riot_event_projection", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.project_game_notification


project = load_projector()


def alias(value: str) -> str:
    return "id-" + hashlib.sha256(b"test-salt" + value.encode()).hexdigest()[:12]


def test_decodes_nested_notification_json_and_preserves_gameplay_evidence() -> None:
    payload = {
        "message": json.dumps(
            {
                "payload": json.dumps(
                    {
                        "stats": {
                            "killCount": 4,
                            "deathCount": 2,
                            "numKills": "4",
                            "roundIndex": 3,
                        },
                        "subject": "owned",
                        "killer": "owned",
                        "victim": "other",
                        "type": "kill",
                    }
                )
            }
        )
    }
    result = project(payload, alias=alias, subject="owned", decode_json=True)
    facts = result["message"]["value"]["payload"]["value"]
    assert facts["stats"] == {"killCount": 4, "deathCount": 2, "numKills": 4, "roundIndex": 3}
    assert facts["subject"] == facts["killer"] == {"alias": alias("owned"), "self": True}
    assert facts["victim"] == {"alias": alias("other"), "self": False}
    assert facts["type"] == "kill"


def test_names_routes_chat_and_secrets_never_survive_projection() -> None:
    result = project(
        {
            "PrivatePlayerName": {"kills": 4},
            "uri": "/players/PrivatePlayerName",
            "accessToken": "secret-token",
            "message": "private chat text",
            "password": {"kills": 99},
            "payload": json.dumps({"name": "OtherPrivateName"}),
        },
        alias=alias,
    )
    encoded = json.dumps(result)
    for private in (
        "PrivatePlayerName",
        "OtherPrivateName",
        "secret-token",
        "private chat text",
        "/players/",
    ):
        assert private not in encoded
    assert result[alias("PrivatePlayerName")] == {"kills": 4}
    assert result[alias("accessToken")] == {"type": "redacted"}
    assert result[alias("password")] == {"type": "redacted"}


def test_malformed_oversized_and_deep_encoded_envelopes_are_bounded() -> None:
    assert (
        project({"payload": "{bad"}, alias=alias, decode_json=True)["payload"]["type"] == "string"
    )
    huge = '{"kills": 4, "text": "' + "x" * 131_072 + '"}'
    assert project({"payload": huge}, alias=alias, decode_json=True)["payload"]["type"] == "string"
    nested: object = {"kills": 4}
    for _ in range(20):
        nested = {"data": nested}
    assert '"type": "limit"' in json.dumps(project(nested, alias=alias))


def test_generic_projection_keeps_message_redaction_and_does_not_decode_strings() -> None:
    payload = {"message": {"kills": 9}, "payload": '{"kills": 9}', "chat": {"deaths": 4}}
    result = project(payload, alias=alias)
    assert result["message"] == {"type": "redacted"}
    assert result[alias("chat")] == {"type": "redacted"}
    assert result["payload"]["type"] == "string"
    assert project(payload, alias=alias, decode_json=True)[alias("chat")] == {"type": "redacted"}


def test_unknown_and_nonfinite_numbers_are_not_saved_as_gameplay_facts() -> None:
    result = project(
        {
            "kills": 10**1_000,
            "deaths": float("nan"),
            "assists": float("inf"),
            "arbitraryNumber": 123456789,
            "health": 87.5,
        },
        alias=alias,
    )
    assert result["kills"] == result["deaths"] == result["assists"] == {"type": "number"}
    assert result[alias("arbitraryNumber")] == {"type": "number"}
    assert result["health"] == 87.5


def test_broader_combat_economy_ability_and_objective_numbers_survive() -> None:
    evidence = {
        "damageDealt": 156,
        "damage_taken": 80,
        "healthAfter": 20,
        "armorAfter": 0,
        "shotsFired": 9,
        "shotsHit": 3,
        "ammoInMagazine": 21,
        "reloadTime": 2.5,
        "abilityCharges": 2,
        "ultimatePoints": 6,
        "cooldownMillis": 12000,
        "creditsBefore": 3900,
        "creditsAfter": 1000,
        "purchaseCost": 2900,
        "plantTime": "3.5",
        "defuseTimeRemaining": "7.125",
        "spikeTimer": 31,
        "roundIndex": 4,
        "roundStartTime": "1777777777777",
        "roundsWon": 3,
        "combatScore": 240,
        "clutchAttempts": 1,
        "tradeKills": 2,
        "enemiesAlive": 1,
    }
    expected = {
        **evidence,
        "plantTime": 3.5,
        "defuseTimeRemaining": 7.125,
        "roundStartTime": 1777777777777,
    }
    assert project(evidence, alias=alias) == expected


def test_technical_enums_are_case_insensitive_and_identifiers_are_only_aliased() -> None:
    result = project(
        {
            "eventType": "ONROUNDENDED",
            "phase": "BUY_PHASE",
            "result": "VICTORY",
            "weaponId": "/Game/Weapons/Rifle/Example.Example_C",
            "characterId": "private-character",
            "mapId": "private-map",
            "abilityId": "private-ability",
            "isClutch": True,
        },
        alias=alias,
    )
    assert result["eventType"] == "OnRoundEnded"
    assert result["phase"] == "buy_phase" and result["result"] == "victory"
    assert result["isClutch"] is True
    for key in ("weaponId", "characterId", "mapId", "abilityId"):
        assert result[key]["alias"].startswith("id-")
    encoded = json.dumps(result)
    assert "/Game/Weapons" not in encoded and "private-" not in encoded


def test_expanded_schema_still_hides_name_keyed_maps_and_credentials() -> None:
    payload = {
        "damageEvents": [
            {"PrivatePlayerName": {"damageDealt": 40}, "weaponName": "Private weapon text"}
        ],
        "abilities": {"PrivateAbilityName": {"charges": 1}},
        "creditsToken": "secret-credential",
        "chat": {"damageDealt": 99},
        "eventName": "PrivatePlayerName",
        "resource": "/players/PrivatePlayerName",
    }
    result = project({"message": json.dumps(payload)}, alias=alias, decode_json=True)
    encoded = json.dumps(result)
    for private in (
        "PrivatePlayerName",
        "PrivateAbilityName",
        "Private weapon text",
        "secret-credential",
        "creditsToken",
    ):
        assert private not in encoded
    facts = result["message"]["value"]
    assert facts["damageEvents"]["items"][0][alias("PrivatePlayerName")] == {"damageDealt": 40}
    assert facts[alias("creditsToken")] == {"type": "redacted"}


def test_safe_performance_and_network_signals_remain_numeric() -> None:
    payload = {
        "performance": {"fps": 240, "frameTime": 4.1, "frameTimeMs": "4.1"},
        "network": {
            "ping": 24,
            "latency": 12,
            "rtt": 24,
            "packetLoss": 2,
            "packetLossPercent": 0.5,
        },
    }
    result = project(payload, alias=alias)
    assert result["performance"] == {"fps": 240, "frameTime": 4.1, "frameTimeMs": 4.1}
    assert result["network"] == payload["network"]
