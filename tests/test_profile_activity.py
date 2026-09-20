from dataclasses import replace
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from peaks.adapters.persistence.database import Database
from peaks.adapters.persistence.player_profiles import cached_profile, remember_profile
from peaks.adapters.persistence.profile_history import observe_profile
from peaks.adapters.riot.league import LeagueSummonerProfile
from peaks.adapters.riot.valorant import ValorantClient
from peaks.application.runtime import RiotSearchService
from peaks.bridge import Bridge, _match
from peaks.domain.models import Account, Game, MatchRecord


def test_activity_survives_restart_without_counting_imported_matches_as_logins(tmp_path):
    filename = tmp_path / 'activity.sqlite'
    with Database(filename) as database:
        database.add_account(Account('one', 'Owner', 'TEST', 'EUW', 'subject'))
        database.add_account(Account('two', 'Other', 'TEST', 'EUW', 'another'))
        record = MatchRecord.from_dict({'match_id': 'match-one', 'account_id': 'one', 'game': 'valorant', 'played_at': '2026-09-10T12:00:00+00:00', 'duration_seconds': 1800, 'rank_delta': 0, 'result': 'win'})
        database.add_match(record)
        database.add_match(record)
        for day in (18, 18, 19):
            observe_profile(database, 'one', 'connection', {}, now=datetime(2026, 9, day, 12, tzinfo=UTC))
        for rating in (0, 0, 22):
            observe_profile(database, 'one', 'rank', {'game': 'VALORANT', 'tier': 'ascendant', 'division': '3', 'rating': rating})
        assert database.profile_activity('two')['matches'] == []
        assert database.get_account_match('two', 'match-one') is None
    with Database(filename) as database:
        data = database.profile_activity('one')
        assert len(data['matches']) == 1
        assert data['matches'][0]['durationSeconds'] == 1800
        assert data['matches'][0]['delta'] == '0'
        assert len(data['connectionDays']) == 2
        assert [rank['rating'] for rank in data['ranks']] == [0, 22]
        assert data['identities'][0]['riotId'] == 'Owner#TEST'
        assert _match(database.get_account_match('one', 'match-one'))['delta'] == '+0 RR'
        database.remove_account('one')
        assert database.profile_activity('one')['identities'] == []


def test_new_history_reads_require_unlock_and_an_owned_account(monkeypatch):
    monkeypatch.setenv('PEAKS_DEMO', '1')
    bridge = Bridge()
    for command in ('account_activity', 'account_match'):
        bridge._locked = True
        with pytest.raises(PermissionError):
            bridge.handle(command, {'accountId': 'anything'})
        bridge._locked = False
        with pytest.raises(ValueError):
            bridge.handle(command, {'accountId': 'not-an-owned-account'})
    with Database() as database:
        database.add_account(Account('one', 'Owner', 'TEST', 'EUW', 'subject'))
        database.add_match(MatchRecord.from_dict({'id': 'archived', 'account_id': 'one', 'game': 'valorant', 'played_at': '2025-03-10T12:00:00+00:00', 'duration_seconds': 1800, 'metadata': {'teams': [{'name': 'Team', 'players': [{'name': 'Owner#TEST', 'self': True, 'stats': {'kills': 10}}]}]}}))
        bridge.demo = False
        bridge._repository = database
        bridge._renderer_account_handles = {'one': 'opaque-one'}
        bridge.accounts = [{'id': 'one', 'riotId': 'Owner#TEST', 'owned': True}]
        activity = bridge.handle('account_activity', {'accountId': 'opaque-one'})
        assert activity['matches'][0]['id'] == 'archived'
        assert 'teams' not in activity['matches'][0]
        report = bridge.handle('account_match', {'accountId': 'opaque-one', 'matchId': 'archived'})
        assert report['durationSeconds'] == 1800
        assert report['teams'][0]['players'][0]['stats']['kills'] == 10


def test_partial_refresh_does_not_erase_accumulated_evidence():
    with Database() as database:
        database.add_account(Account('one', 'Owner', 'TEST', 'EUW', 'subject'))
        complete = MatchRecord.from_dict({'id': 'match-one', 'account_id': 'one', 'game': 'valorant', 'played_at': '2026-09-10T12:00:00+00:00', 'duration_seconds': 1800, 'rank_delta': 25, 'result': 'win', 'metadata': {'teams': [{'name': 'Team', 'players': [{'name': 'Owner#TEST', 'self': True, 'stats': {'kills': 10}}]}]}})
        database.add_match(complete)
        database.add_match(replace(complete, duration_seconds=None, rank_delta=None, metadata={'teams': []}))
        restored = database.get_account_match('one', 'match-one')
        assert restored.duration_seconds == 1800 and restored.rank_delta == 25
        assert restored.metadata == complete.metadata
        # Explicitly refreshed hidden rosters replace older visible evidence.
        hidden = {'teams': [{'name': 'Team', 'players': [{'hidden': True}]}]}
        database.add_match(replace(complete, rank_delta=0, metadata=hidden))
        assert database.get_account_match('one', 'match-one').metadata == hidden
        assert database.get_account_match('one', 'match-one').rank_delta == 0


def test_public_cache_preserves_each_game_and_rank_observations_but_never_credentials():
    with Database() as database:
        initial = {'id': 'puuid-one', 'riotId': 'Player#TEST', 'ranks': [{'game': 'VALORANT', 'tier': 'Ascendant', 'division': '3', 'rating': 0}], 'matches': [{'id': f'{game}-{i}', 'game': game, 'playedAtTimestamp': 100 + i, 'teams': [{'name': 'Team', 'players': []}]} for game in ('VALORANT', 'League of Legends', 'Teamfight Tactics') for i in range(25)], 'token': 'secret', 'cookies': {'ssid': 'secret'}}
        first = remember_profile(database, initial, now=1000)
        assert len(first['matches']) == 60
        assert 'secret' not in repr(first)
        second = remember_profile(database, {'id': 'puuid-one', 'riotId': 'Player#TEST', 'ranks': [], 'matches': []}, now=1100)
        assert len(second['matches']) == 60
        assert len(second['activity']['ranks']) == 1
        assert cached_profile(database, 'PLAYER#test', now=1200) == second
        assert cached_profile(database, 'someone#test', now=1200) is None
        assert cached_profile(database, 'Player#TEST', now=1100 + 91 * 86400) is None
        other = remember_profile(database, {'id': 'puuid-two', 'riotId': 'Player#TEST', 'ranks': [], 'matches': []}, now=1200)
        assert other['matches'] == []
        assert other['activity']['ranks'] == []


def test_tft_damage_aliases_and_empty_lobby_fields_are_not_false_zeroes():
    players = [{'puuid': 'owner', 'total_damage_to_players': 0}, {'puuid': 'other', 'totalDamageToPlayers': 0}]
    def view():
        return _match(RiotSearchService._match_view('TFT', 'EUW1_one', puuid='owner', info={'participants': players, 'game_length': 2000}))['teams']
    assert all('damage' not in player['stats'] for team in view() for player in team['players'])
    players[1]['totalDamageToPlayers'] = 98
    teams = view()
    assert sorted(player['stats']['damage'] for team in teams for player in team['players']) == [0, 98]
    players[0]['totalDamageToPlayers'] = 130
    assert next(player for team in view() for player in team['players'] if player['self'])['stats']['damage'] == 130
    saved = {'game': 'tft', 'teams': [{'name': 'Lobby', 'players': [{'name': 'A', 'stats': {'damage': 0}}, {'name': 'B', 'stats': {'damage': 0}}, {'name': 'C', 'stats': None}]}]}
    assert all('damage' not in player.get('stats', {}) for team in _match(saved)['teams'] for player in team['players'])


def test_tft_duration_ends_at_the_players_elimination():
    row = RiotSearchService._match_view('TFT', 'EUW1_one', puuid='owner', info={'game_length': 2100, 'participants': [{'puuid': 'owner', 'time_eliminated': 1560.5}]})
    assert row['duration_seconds'] == 1560


def test_competitive_rr_page_is_owner_bound_and_rejects_invalid_rewards():
    paths = []
    def get_json(path):
        paths.append(path)
        return {'Matches': [{'MatchID': 'zero', 'RankedRatingEarned': 0}, {'MatchID': 'loss', 'RankedRatingEarned': -19}, {'MatchID': '../invalid', 'RankedRatingEarned': 10}, {'MatchID': 'bad', 'RankedRatingEarned': True}, *[{'MatchID': f'game-{i}', 'RankedRatingEarned': 22} for i in range(25)]]}
    client = ValorantClient(SimpleNamespace(get_json=get_json), 'verified-owner')
    deltas = client.competitive_deltas_optional()
    assert deltas['zero'] == 0 and deltas['loss'] == -19
    assert '../invalid' not in deltas and 'bad' not in deltas
    assert 'game-16' not in deltas
    assert paths == ['/mmr/v1/players/verified-owner/competitiveupdates?startIndex=0&endIndex=20&queue=competitive']


def test_local_public_profile_populates_lol_and_tft_and_normalizes_the_requested_player():
    calls = []
    def history(profile, *, game, limit):
        calls.append((profile.puuid, game, limit))
        return {'games': [{'metadata': {'match_id': f'EUW1_{game}'}, 'info': {'gameCreation': 1789900000000, 'gameDuration': 1800, 'participants': [{'puuid': 'target', 'kills': 12, 'deaths': 4, 'assists': 5, 'placement': 3, 'units': [{'character_id': 'DA_Sentinel18', 'tier': 2}]}]}}]}
    service = RiotSearchService(local_client_factory=lambda: SimpleNamespace(
        lookup_summoner=lambda *args, **kwargs: LeagueSummonerProfile('target', 'Target', 'TEST', region='EUW'),
        ranked_stats=lambda _: (), public_match_history=history, close=lambda: None,
    ))
    result = Bridge._player(service._local_search_player('Target#TEST', region='EUW', requested='all')[0])
    assert calls == [('target', 'League', 20), ('target', 'TFT', 20)]
    assert {match['game'] for match in result['matches']} == {Game.LEAGUE_OF_LEGENDS.label, Game.TFT.label}
    assert all(match['durationSeconds'] == 1800 for match in result['matches'])
    assert all(next(player for team in match['teams'] for player in team['players'] if player['self'])['riotId'] == 'Target#TEST' for match in result['matches'])
