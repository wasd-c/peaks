import {describe, expect, it} from 'vitest'

import {matchPlayerProfile, playerIsFollowed, playerIsWatched, samePlayerIdentity} from './playerProfiles'
import type {Player} from './types'

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
