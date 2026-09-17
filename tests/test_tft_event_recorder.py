"""The passive TFT recorder records gameplay facts without private payloads."""

import json
from pathlib import Path

from scripts.record_tft_events import (
    LogTail,
    number,
    project_eog,
    project_flow,
    project_log_line,
    project_tft_snapshot,
)


def test_log_records_only_known_signals_and_numeric_fields() -> None:
    line = '[2026.09.17-19.53.49:147][123]TFTRoundSubsystem: User PrivateName#TAG round=12 health=48 secret-value'
    result = project_log_line(line)
    assert result == {
        'sourceTime': '2026.09.17-19.53.49:147',
        'signals': ['health', 'round'],
        'numbers': [{'field': 'round', 'value': 12}, {'field': 'health', 'value': 48}],
    }
    assert 'PrivateName' not in json.dumps(result)
    assert 'secret-value' not in json.dumps(result)


def test_log_ignores_auth_chat_unknown_and_oversized_lines() -> None:
    for line in ('Authorization: Bearer abc health=48', 'chat health=48 PrivateName', 'cookie=x gold=22', 'arbitrary payload', 'x' * 65537):
        assert project_log_line(line) is None


def test_eog_keeps_tactician_health_and_aliases_only() -> None:
    payload = {
        'gameId': 112233, 'queueId': 1160, 'secret': 'never-save',
        'statsBlock': {'gameLengthSeconds': 1000, 'players': [{
            'PUUID': 'private-puuid', 'riotIdGameName': 'PrivateName', 'riotIdTagLine': 'TAG',
            'health': 48, 'ffaStanding': 2, 'partnerGroupId': 1, 'augments': [{'name': 'x'}],
            'boardPieces': [{}, {}], 'token': 'never-save',
        }]},
    }
    result = project_eog(payload, alias=lambda _: 'id-alias', own_puuid='private-puuid')
    assert result is not None
    assert result['players'] == [{
        'self': True, 'player': 'id-alias', 'health': 48, 'ffaStanding': 2, 'partnerGroupId': 1,
        'augmentsCount': 1, 'boardPiecesCount': 2,
    }]
    serialized = json.dumps(result)
    for private in ('private-puuid', 'PrivateName', 'TAG', 'never-save', '112233'):
        assert private not in serialized


def test_eog_rejects_malformed_health_without_dropping_zero() -> None:
    result = project_eog({'statsBlock': {'players': [
        {'health': True}, {'health': 0}, {'health': -1}, {'health': 256}, {'health': float('nan')},
    ]}}, alias=lambda _: 'alias')
    assert result is not None
    assert result['players'] == [{'self': False}, {'self': False, 'health': 0}, {'self': False}, {'self': False}, {'self': False}]


def test_flow_drops_connection_credentials_and_roster_identifiers() -> None:
    result = project_flow({
        'phase': 'InProgress', 'gameClient': {'running': True, 'serverIp': '1.2.3.4'},
        'gameData': {'gameId': 123, 'password': 'private', 'spectatorKey': 'private',
                     'queue': {'id': 1100}, 'teamOne': [{'puuid': 'private'}] * 8, 'teamTwo': []},
    }, alias=lambda _: 'id-match')
    assert result == {'phase': 'InProgress', 'queueId': 1100, 'match': 'id-match', 'gameClientRunning': True, 'teamSizes': [8, 0]}
    assert 'private' not in json.dumps(result)


def test_tail_tracks_append_partial_line_and_truncation(tmp_path: Path) -> None:
    filename = tmp_path / 'TFT.log'
    filename.write_bytes(b'health=100\nround=')
    tail = LogTail(filename)
    assert len(tail.read()) == 1
    assert tail.read() == []
    with filename.open('ab') as handle:
        handle.write(b'2\n')
    assert tail.read()[0]['numbers'] == [{'field': 'round', 'value': 2}]
    filename.write_bytes(b'hp=0\n')
    assert tail.read()[0]['numbers'] == [{'field': 'hp', 'value': 0}]


def test_numeric_validation_is_finite_and_bounded() -> None:
    assert number(True) is None
    assert number(float('inf')) is None
    assert number(-1) is None
    assert number(1_000_001) is None
    assert number(0) == 0


def test_tft_file_snapshots_can_show_changing_health_during_live_match() -> None:
    def alias(value: str) -> str:
        return 'alias-' + value
    session = project_flow({'phase': 'InProgress', 'gameClient': {'running': True}, 'gameData': {'gameId': 42, 'queue': {'id': 1100}}}, alias=alias)
    snapshots = []
    for health in (91, 82, 73):
        snapshots.append(project_tft_snapshot({
            'gameId': 42, 'queueId': 1100,
            'statsBlock': {'players': [{'PUUID': 'own', 'health': health}]},
        }, alias=alias, session=session, own_puuid='own'))
    assert all(snapshot is not None and snapshot['currentMatch'] is True for snapshot in snapshots)
    assert [snapshot['stats']['players'][0]['health'] for snapshot in snapshots] == [91, 82, 73]
    assert all(snapshot['source'] == 'TFTEoGStats.json' for snapshot in snapshots)


def test_tft_snapshot_binding_rejects_old_game_queue_and_inactive_session() -> None:
    def alias(value: str) -> str:
        return 'alias-' + value
    payload = {'gameId': 42, 'queueId': 1100, 'statsBlock': {'players': [{'health': 73}]}}
    for session in (
        None,
        {'phase': 'InProgress', 'gameClientRunning': True, 'match': 'alias-41', 'queueId': 1100},
        {'phase': 'InProgress', 'gameClientRunning': True, 'match': 'alias-42', 'queueId': 1160},
        {'phase': 'EndOfGame', 'gameClientRunning': True, 'match': 'alias-42', 'queueId': 1100},
        {'phase': 'InProgress', 'gameClientRunning': False, 'match': 'alias-42', 'queueId': 1100},
        {'phase': 'InProgress', 'gameClientRunning': True, 'match': None, 'queueId': None},
    ):
        result = project_tft_snapshot(payload, alias=alias, session=session)
        assert result is not None and result['currentMatch'] is False
