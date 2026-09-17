"""Project bounded Riot game notifications without recording private strings."""

from __future__ import annotations

import json
import math
import re
from collections.abc import Callable

_SECRET = re.compile(
    r"password|token|secret|authorization|cookie|credential|email|phone|jwt|chat", re.I
)
_IDENTITY = re.compile(
    r"^(?:puuid|subject|playerId|matchId|partyId|killer|victim|userId|attackerId|victimId|"
    r"sourceId|targetId|weaponId|characterId|agentId|mapId|abilityId|itemId|skinId|damageSourceId)$",
    re.I,
)
_NUMBER = re.compile(
    r"^(?:(?:total|round|num)?(?:kills?|deaths?|assists?|headshots?)(?:count)?|"
    r"round(?:s|number|index|count|played)?|score|damage|health|alive|time|timestamp|"
    r"roundTime|timeSinceRoundStartMillis|matchScoreAllyTeam|matchScoreEnemyTeam|"
    r"partyOwnerMatchScoreAllyTeam|partyOwnerMatchScoreEnemyTeam|partySize|maxPartySize)$",
    re.I,
)
_CONTAINERS = frozenset({"payload", "message", "data", "body", "content"})
_GAME_NUMBERS = frozenset(
    """
    damageDealt damageTaken damageReceived damageBlocked totalDamage damageAmount damagePerRound
    damageDelta remainingHealth currentHealth maxHealth healthBefore healthAfter healing healingDone
    healingReceived armor armour shields shield currentArmor maxArmor armorBefore armorAfter
    shieldBefore shieldAfter shieldDamage bodyshots legshots shots shotsFired shotsHit shotsMissed
    shotCount hitCount bulletCount bullets ammo ammoCount ammoInClip ammoInMagazine ammoReserve
    reserveAmmo magazineAmmo clipAmmo magazineSize clipSize reloadCount reloadTime reloadDuration
    weaponEquipTime equipDuration fireRate distance wallbangCount penetrationCount
    abilityCharges charges chargesRemaining abilityCount abilityCasts casts castCount
    ability1Casts ability2Casts grenadeCasts ultimateCasts ultimatePoints ultPoints ultimateCost
    pointsToUltimate ultimatePointsRequired abilityCooldown cooldown cooldownRemaining cooldownSeconds
    cooldownMillis duration durationMillis durationSeconds elapsedMillis elapsedSeconds timeRemaining
    timeRemainingMillis timeRemainingSeconds credits creditsBefore creditsAfter creditsSpent
    creditsEarned creditsRemaining startingCredits endingCredits economyRating loadoutValue
    equipmentValue money moneySpent moneyEarned purchaseCount purchaseCost cost price refundAmount
    plants defuses plantCount defuseCount plantTime defuseTime spikeTimer spikeTimeRemaining
    plantTimeRemaining defuseTimeRemaining plantDuration defuseDuration detonationTime
    detonationTimeRemaining roundStartTime roundEndTime roundDuration roundDurationMillis
    roundTimeMillis roundTimeSeconds matchTime matchTimeMillis matchDuration roundsWon roundsLost
    roundsRemaining matchScore teamScore opponentScore combatScore averageCombatScore acs
    firstKills firstDeaths multiKills doubleKills tripleKills quadKills aces clutchKills clutchCount
    clutchAttempts clutchWins tradeKills tradedDeaths tradeCount alivePlayers playersAlive
    alliesAlive enemiesAlive teammatesAlive opponentsAlive advantage deficit streak killStreak
    survivalTime timeToKill timeSinceLastKill timeSinceLastDeath timeSinceRoundStart
    fps frameTime frameTimeMs ping latency rtt packetLoss packetLossPercent
    """.casefold().split()
)


def _game_number(key: str) -> bool:
    return bool(_NUMBER.fullmatch(key)) or key.casefold().replace("_", "") in _GAME_NUMBERS


_SCHEMA = (
    frozenset(
        {
            "event",
            "events",
            "eventtype",
            "eventname",
            "type",
            "resource",
            "uri",
            "service",
            "version",
            "state",
            "phase",
            "sessionloopstate",
            "stats",
            "players",
            "player",
            "teams",
            "team",
            "teamid",
            "roundresults",
            "results",
            "puuid",
            "subject",
            "playerid",
            "matchid",
            "partyid",
            "userid",
            "killer",
            "victim",
            "matchpresencedata",
            "partypresencedata",
            "isvalid",
            "ispartyowner",
        }
    )
    | _CONTAINERS
    | frozenset(
        """
        combat damageEvents damageDetails damageType hit hitResult hitLocation shots shotEvents
        weapon weapons equippedWeapon inventory equipment ammoState reloadState ability abilities
        abilityEvents abilityState ultimate economy purchases purchase refunds objective objectives
        spike spikeState bombState round roundState roundPhase matchPhase matchState result outcome
        roundResult winningTeam winningTeamId playerStats teamStats combatEvents killEvents
        isAlive isDead isReloading isEquipped isPlanting isDefusing isSpikePlanted isSpikeDefused
        isHeadshot isWallbang isFirstKill isFirstDeath isTrade isTraded isClutch isWinner didWin won
        weaponId characterId agentId mapId abilityId itemId skinId damageSourceId attackerId
        victimId sourceId targetId performance network
        """.casefold().split()
    )
)
_ENUMS = frozenset(
    {
        "Create",
        "Update",
        "Delete",
        "INGAME",
        "PREGAME",
        "MENUS",
        "INQUEUE",
        "MATCHMAKING",
        "DISABLED",
        "kill",
        "death",
        "assist",
        "match_start",
        "match_end",
        "shopping",
        "combat",
        "end",
        "game_end",
        "core-game",
        "pre-game",
        "match-details",
        "party",
        "true",
        "false",
        "damage",
        "damaged",
        "healing",
        "healed",
        "headshot",
        "bodyshot",
        "legshot",
        "shot",
        "fired",
        "hit",
        "miss",
        "reload",
        "reloading",
        "reloaded",
        "equip",
        "equipped",
        "ability",
        "ability_cast",
        "ultimate",
        "ultimate_cast",
        "ultimate_ready",
        "cooldown",
        "purchase",
        "purchased",
        "buy",
        "bought",
        "sell",
        "sold",
        "refund",
        "refunded",
        "plant",
        "planting",
        "planted",
        "defuse",
        "defusing",
        "defused",
        "detonate",
        "detonated",
        "spike_planted",
        "spike_defused",
        "spike_dropped",
        "spike_picked_up",
        "spike_detonated",
        "round_start",
        "round_end",
        "round_won",
        "round_lost",
        "buy_phase",
        "combat_phase",
        "post_round",
        "overtime",
        "sudden_death",
        "halftime",
        "postgame",
        "in_progress",
        "win",
        "won",
        "loss",
        "lost",
        "victory",
        "defeat",
        "draw",
        "clutch",
        "trade",
        "elimination",
        "eliminated",
        "ace",
        "first_blood",
        "attack",
        "defense",
        "attacker",
        "defender",
        "OnRoundStarted",
        "OnRoundEnded",
        "OnPlayerKilled",
        "OnPlayerDied",
        "OnDamageTaken",
        "OnDamageDealt",
        "OnWeaponFired",
        "OnWeaponEquipped",
        "OnReloadStarted",
        "OnReloadEnded",
        "OnAbilityUsed",
        "OnUltimateUsed",
        "OnSpikePlanted",
        "OnSpikeDefused",
        "OnMatchEnded",
        "WaitingToStart",
        "WaitingToPostMatch",
        "InProgress",
        "InGame",
        "MainMenu",
    }
)
_ENUM_LOOKUP = {value.casefold(): value for value in sorted(_ENUMS)}


def project_game_notification(
    value: object,
    *,
    alias: Callable[[str], str],
    subject: str | None = None,
    decode_json: bool = False,
) -> object:
    """Decode notification envelopes in memory, then keep only safe evidence.

    The caller supplies its per-recording salted alias function. Unknown keys,
    routes, names and arbitrary strings never survive as literal text. This is
    intended only for Riot's game-notification channel, not chat recording.
    """
    remaining_nodes = 2_048
    remaining_decode_chars = 262_144

    def project(item: object, key: str = "", depth: int = 0) -> object:
        nonlocal remaining_nodes, remaining_decode_chars
        if depth > 8 or remaining_nodes <= 0:
            return {"type": "limit"}
        remaining_nodes -= 1
        # Fixed gameplay fields such as clutchAttempts can contain the letters
        # "chat" across word boundaries; that is not a private chat branch.
        if (_SECRET.search(key) and not _game_number(key)) or (
            not decode_json and "message" in key.casefold()
        ):
            return {"type": "redacted"}
        if item is None or isinstance(item, bool):
            return item
        if isinstance(item, (int, float)):
            if _game_number(key) and abs(item) <= 10**15 and math.isfinite(item):
                return item
            return {"type": "number"}
        if isinstance(item, str):
            if (
                decode_json
                and key.casefold() in _CONTAINERS
                and len(item) <= min(131_072, remaining_decode_chars)
            ):
                text = item.strip()
                if text.startswith(("{", "[")):
                    remaining_decode_chars -= len(item)
                    try:
                        decoded = json.loads(text)
                    except (ValueError, RecursionError):
                        pass
                    else:
                        return {"encoding": "json", "value": project(decoded, "", depth + 1)}
            if _IDENTITY.fullmatch(key) and 1 <= len(item) <= 256:
                return {"alias": alias(item), "self": bool(subject and item == subject)}
            if item.casefold() in _ENUM_LOOKUP:
                return _ENUM_LOOKUP[item.casefold()]
            if _game_number(key) and re.fullmatch(r"-?[0-9]{1,16}(?:\.[0-9]{1,6})?", item):
                number = float(item) if "." in item else int(item)
                if abs(number) <= 10**15:
                    return number
            return {"type": "string", "length": min(len(item), 131_072)}
        if isinstance(item, list):
            return {
                "length": len(item),
                "items": [project(child, key, depth + 1) for child in item[:20]],
            }
        if isinstance(item, dict):
            result: dict[str, object] = {}
            for child_key, child in list(item.items())[:80]:
                if not isinstance(child_key, str):
                    continue
                safe_key = (
                    child_key
                    if child_key.casefold() in _SCHEMA or _game_number(child_key)
                    else alias(child_key)
                )
                result[safe_key] = project(child, child_key, depth + 1)
            return result
        return {"type": "unsupported"}

    return project(value)
