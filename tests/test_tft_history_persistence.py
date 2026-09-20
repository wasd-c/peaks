from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from peaks.adapters.persistence.database import Database
from peaks.domain.models import Account, Game, MatchRecord, MatchResult

PLAYED = datetime(2026, 9, 20, 12, tzinfo=UTC)


def record(*, account_id='owner', local=False, placement=2, rich=False):
    stats = {'placement': placement, **({'damage': 137, 'level': 9} if rich else {})}
    player = {'name': 'Player#TEST', 'self': True, 'stats': stats}
    if rich:
        player['composition'] = {'units': [{'id': 'ExampleUnit', 'stars': 2}]}
    return MatchRecord(
        'EUW1_123456', account_id, Game.TFT, PLAYED, MatchResult.TOP_4,
        queue='1100', duration_seconds=1900 if rich else 1700,
        rank_delta=24 if rich else None,
        metadata={'teams': [{'name': 'Lobby', 'players': [player]}], **({'localEndOfGame': True} if local else {})},
    )


def add_owner(database, account_id='owner'):
    database.add_account(Account(account_id, 'Player', 'TEST', 'EUW', 'example-subject'))


def test_local_capture_never_replaces_the_same_accounts_final_riot_report():
    with Database() as database:
        add_owner(database)
        final = record(rich=True)
        database.add_match(final)
        local = replace(record(local=True, placement=6), played_at=PLAYED + timedelta(minutes=4), result=MatchResult.PLACEMENT, queue='1090')

        assert database.add_match(local) == final
        assert database.get_account_match('owner', final.match_id) == final
        assert database.list_matches('owner', game=Game.TFT) == [final]
        assert local.metadata['localEndOfGame'] is True


@pytest.mark.parametrize('marker', ['absent', None, False])
def test_riot_report_upgrades_local_capture_clears_marker_and_survives_restart(tmp_path, marker):
    path = tmp_path / 'tft-history.sqlite'
    with Database(path) as database:
        add_owner(database)
        local = record(local=True)
        database.add_match(local)
        # A valid zero LP reward is evidence, and a missing duration does not
        # discard the known local duration for this exact canonical match.
        final = replace(record(rich=True), duration_seconds=None, rank_delta=0)
        if marker != 'absent':
            final = replace(final, metadata={**final.metadata, 'localEndOfGame': marker})
        upgraded = database.add_match(final)
        assert 'localEndOfGame' not in upgraded.metadata
        assert upgraded.metadata['teams'] == final.metadata['teams']
        assert upgraded.duration_seconds == local.duration_seconds
        assert upgraded.rank_delta == 0
        assert database.add_match(local) == upgraded
        assert len(database.list_matches('owner')) == 1

    with Database(path) as database:
        restored = database.get_account_match('owner', local.match_id)
        assert restored == upgraded
        assert database.add_match(local) == restored


def test_riot_id_only_stub_can_be_enriched_locally_and_does_not_clear_provenance():
    with Database() as database:
        add_owner(database)
        local = record(local=True)
        stub = replace(local, metadata={}, result=MatchResult.UNKNOWN, duration_seconds=None, queue=None)
        database.add_match(stub)
        assert database.add_match(local).metadata['localEndOfGame'] is True

        partial = database.add_match(stub)
        assert partial.metadata == local.metadata
        assert partial.result is local.result
        assert partial.duration_seconds == local.duration_seconds
        roster_stub = replace(stub, metadata={'teams': [{'name': 'Lobby', 'players': [{'name': 'Player#TEST', 'self': True, 'stats': {'level': 3}}]}]})
        assert database.add_match(roster_stub) == local
        final = database.add_match(record(rich=True))
        assert 'localEndOfGame' not in final.metadata
        assert len(database.list_matches('owner')) == 1


@pytest.mark.parametrize('placement', [None, True, 0, 9])
def test_invalid_placement_is_not_final_riot_evidence(placement):
    with Database() as database:
        add_owner(database)
        database.add_match(record(placement=placement))
        local = record(local=True)
        assert database.add_match(local).metadata['localEndOfGame'] is True


def test_another_players_placement_does_not_prove_the_accounts_final_report():
    with Database() as database:
        add_owner(database)
        partial = replace(record(), metadata={'teams': [{'name': 'Lobby', 'players': [
            {'name': 'Player#TEST', 'self': True, 'stats': {}},
            {'name': 'Another#TEST', 'stats': {'placement': 2}},
        ]}]})
        database.add_match(partial)
        local = record(local=True)
        assert database.add_match(local).metadata['localEndOfGame'] is True


def test_same_match_id_is_independent_for_each_account():
    with Database() as database:
        add_owner(database)
        add_owner(database, 'other')
        final = record(rich=True)
        local = record(account_id='other', local=True, placement=7)
        database.add_match(final)
        database.add_match(local)
        database.add_match(local)
        assert database.get_account_match('owner', final.match_id) == final
        assert database.get_account_match('other', local.match_id) == local
        assert len(database.list_matches()) == 2


@pytest.mark.parametrize('game', [Game.VALORANT, Game.LEAGUE_OF_LEGENDS])
def test_other_games_keep_normal_refresh_and_privacy_replacement(game):
    with Database() as database:
        add_owner(database)
        previous = replace(record(rich=True), game=game, result=MatchResult.WIN)
        database.add_match(previous)
        incoming = replace(previous, duration_seconds=None, rank_delta=0,
                           metadata={'teams': [{'name': 'Team', 'players': [{'hidden': True}]}]})
        updated = database.add_match(incoming)
        assert updated.metadata == incoming.metadata
        assert updated.duration_seconds == previous.duration_seconds
        assert updated.rank_delta == 0
