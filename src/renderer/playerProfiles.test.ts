import {describe, expect, it} from 'vitest'

import {matchPlayerProfile, mergeRiotProfile, playerIsFollowed, playerIsWatched, samePlayerIdentity} from './playerProfiles'
import type {Account, Player} from './types'

describe('match player profiles', () => {
  it('builds a watchable profile for a visible Riot ID', () => {
    const profile = matchPlayerProfile(
      {
        name: 'Visible#EUW',
        riotId: 'Visible#EUW',
        rank: 'Ascendant 3',
        agent: 'Sova',
        stats: {kills: 21, deaths: 12, assists: 8},
      },
      {game: 'VALORANT', label: '42 min ago', team: 'Your team', map: 'Abyss'},
    )

    expect(profile?.riotId).toBe('Visible#EUW')
    expect(profile?.currentRank).toBe('Ascendant 3')
    expect(profile?.context?.stats?.kills).toBe(21)
  })

  it('never creates a profile for a hidden or unresolved player', () => {
    expect(matchPlayerProfile(
      {name: 'Hidden player 1', riotId: 'Leaked#ID', hidden: true},
      {game: 'VALORANT', label: 'Live match'},
    )).toBeNull()
    expect(matchPlayerProfile(
      {name: 'Player 2'},
      {game: 'VALORANT', label: 'Live match'},
    )).toBeNull()
  })

  it('keeps current rank, peak and account level when opening a completed-match player', () => {
    const profile = matchPlayerProfile({
      name: 'Returned#EU', riotId: 'Returned#EU', rank: 'Diamond 3',
      currentRank: 'Ascendant 2', peakRank: 'Immortal 1', accountLevel: 284,
    }, {game: 'VALORANT', label: 'Match report'})
    expect(profile).toMatchObject({currentRank: 'Ascendant 2', peakRank: 'Immortal 1', level: 284})
  })

  it('matches watched players by Riot ID even when their local IDs differ', () => {
    const profile = {id: 'match-id', riotId: 'Visible#EUW', region: 'EUW'} as Player
    const followed = [{id: 'stored-puuid', riotId: 'visible#euw', region: 'EUW'} as Player]
    expect(playerIsWatched(profile, followed)).toBe(true)
    expect(playerIsFollowed(profile, followed)).toBe(true)
  })

  it('does not merge different Riot IDs that reuse a provider id', () => {
    const first = {id: 'shared-provider-id', riotId: 'First#EUW', region: 'EUW'} as Player
    const second = {id: 'shared-provider-id', riotId: 'Second#EUW', region: 'EUW'} as Player

    expect(samePlayerIdentity(first, second)).toBe(false)
  })
})

describe('Riot identity profiles', () => {
  const selected: Player = {
    id: 'match-player', riotId: 'Visible#EUW', region: 'GLOBAL', game: 'VALORANT',
    currentRank: 'Ascendant 2', peakRank: 'Immortal 1',
    context: {label: 'Live', character: 'Sova', map: 'Ascent', stats: {kills: 12}},
  }
  const account: Account = {
    id: 'owned', riotId: 'visible#euw', region: 'EUW',
    ranks: [{game: 'Teamfight Tactics', tier: 'Gold III', rating: 0}],
    peakRanks: [{game: 'Teamfight Tactics', tier: 'Platinum II'}],
    matches: [{id: 'tft-1', game: 'Teamfight Tactics', result: 'Top 4'}],
  }

  it('combines owned, watched and fetched games while preserving the selected encounter', () => {
    const watched: Player = {...selected, id: 'saved', matches: [{id: 'val-1', game: 'VALORANT', result: 'Win'}]}
    const fetched: Player = {id: 'search', riotId: 'Visible#EUW', region: 'EUW', game: 'League of Legends', ranks: [{game: 'League of Legends', tier: 'Diamond IV', rating: 50}]}
    const result = mergeRiotProfile(selected, [account], [watched], [fetched])
    expect(result.ranks).toEqual(expect.arrayContaining([
      {game: 'VALORANT', tier: 'Ascendant 2'},
      {game: 'Teamfight Tactics', tier: 'Gold III', rating: 0},
      {game: 'League of Legends', tier: 'Diamond IV', rating: 50},
    ]))
    expect(result.peakRanks).toHaveLength(2)
    expect(result.matches?.map(match => match.id)).toEqual(['tft-1', 'val-1'])
    expect(result.region).toBe('EUW')
    expect(result.id).toBe(selected.id)
    expect(result.game).toBe('VALORANT')
    expect(result.context).toBe(selected.context)
  })

  it('never mixes other Riot identities even with reused local identifiers or a changed #tag', () => {
    const result = mergeRiotProfile(selected, [{...account, riotId: 'Visible#OTHER'}], [{...selected, riotId: 'Other#EUW', ranks: [{game: 'League of Legends', tier: 'Challenger'}]}], [{...selected, riotId: 'Other#EUW', matches: account.matches}])
    expect(result.games).toEqual(['VALORANT'])
    expect(result.ranks).toEqual([{game: 'VALORANT', tier: 'Ascendant 2'}])
    expect(result.matches).toEqual([])
  })

  it('retains known ranks on a partial refresh and deduplicates history within each game', () => {
    const fetched: Player = {...selected, ranks: [{game: 'Teamfight Tactics', tier: 'Rank unavailable'}], matches: [
      {id: 'tft-1', game: 'Teamfight Tactics', result: 'Top 4', score: '#2'},
      {id: 'tft-1', game: 'VALORANT', result: 'Win'},
    ]}
    const result = mergeRiotProfile(selected, [account], [], [fetched])
    expect(result.ranks).toContainEqual(account.ranks[0])
    expect(result.matches).toHaveLength(2)
    expect(result.matches?.[0].score).toBe('#2')
  })

  it('does not infer a game or an unranked status from an identity-only result', () => {
    const result = mergeRiotProfile({id: 'identity', riotId: 'Identity#EU', region: 'GLOBAL'}, [], [])
    expect(result.games).toEqual([])
    expect(result.ranks).toEqual([])
  })
})
