import {describe, expect, it} from 'vitest'
import {aggregateProfile, approvedProfileAccount, filterProfileMatches, profileBreakdown, profileMatches, profilePlayer} from './accountProfile'
import type {AppState, Match, PlayerStats} from './types'

const match = (id: string, stats: PlayerStats, extra: Partial<Match> = {}): Match => ({
  id, game: 'VALORANT', result: 'Win', mode: 'competitive', map: 'Ascent', season: 'V26:A5',
  teams: [{name: 'Blue', score: 13, players: [{name: 'OldName#TEST', self: true, agent: 'Omen', stats}]}, {name: 'Red', score: 7, players: []}], ...extra,
})
const kda = {kills: 10, deaths: 5, assists: 2}

describe('account performance', () => {
  it('weights ACS and ADR by rounds, hit rate by hits, and keeps DDA denominators aligned', () => {
    const matches = [
      match('one', {...kda, roundsPlayed: 10, combatScore: 3000, damage: 2000, headshots: 3, bodyshots: 6, legshots: 1, damageReceived: 1000, impactRounds: 10, kastRounds: 8}),
      match('two', {...kda, roundsPlayed: 30, combatScore: 3000, damage: 3000, headshots: 1, bodyshots: 0, legshots: 0, impactRounds: 30, kastRounds: 15}, {result: 'Draw'}),
    ]
    const stats = aggregateProfile(matches, 'NewName#TEST')
    expect(stats.acs).toBe(150)
    expect(stats.adr).toBe(125)
    expect(stats.headshotRate).toBeCloseTo(4 / 11 * 100)
    expect(stats.damageDelta).toBe(100)
    expect(stats.coverage.damageDelta).toBe(1)
    expect(stats.kast).toBeCloseTo(57.5)
    expect(stats.winRate).toBe(50)
    expect(stats.kd).toBe(2)
    expect(stats.kad).toBe(2.4)
  })

  it('does not turn missing details into zeroes, and never uses someone else’s stats', () => {
    const missing = match('empty', {}, {teams: [{name: 'Blue', players: [{name: 'Other#TEST', stats: kda}]}]})
    const stats = aggregateProfile([missing], 'Self#TEST')
    for (const field of ['kills', 'kd', 'acs', 'adr', 'kast', 'headshotRate', 'aces', 'damageDelta'] as const) expect(stats[field]).toBeUndefined()
    expect(stats.detailed).toBe(0)
    expect(profilePlayer(match('duplicate', kda, {teams: [{name: 'Blue', players: [{name: 'a', self: true}, {name: 'b', self: true}]}]}), 'Self#TEST')).toBeUndefined()
  })

  it('filters all aggregates by queue, act, agent and map without double-counting IDs', () => {
    const first = match('one', kda)
    const second = match('two', kda, {mode: 'deathmatch', freeForAll: true, season: 'V26:A4'})
    const league = {...first, id: 'league', game: 'League of Legends' as const}
    const filtered = filterProfileMatches([first, first, second, league], 'Self#TEST', {mode: 'competitive', season: 'V26:A5', agent: 'Omen', map: 'Ascent'})
    expect(filtered).toEqual([first])
    expect(profileMatches([first, first, second, league])).toHaveLength(2)
    expect(profileBreakdown(filtered, 'Self#TEST', 'role')[0]).toMatchObject({label: 'Controller', matches: 1, kd: 2})
    expect(aggregateProfile([second], 'Self#TEST').roundWinRate).toBeUndefined()
  })

  it('reports recorded weapon kills rather than pretending to know weapon accuracy', () => {
    const stats = aggregateProfile([match('one', {...kda, weaponUsage: [{weapon: 'Vandal', kills: 6}, {weapon: 'Sheriff', kills: 2}]})], 'Self#TEST')
    expect(stats.weapons).toEqual([{label: 'Vandal', kills: 6, share: 75}, {label: 'Sheriff', kills: 2, share: 25}])
  })

  it('opens only the identity explicitly returned by successful connection commands', () => {
    const account = {id: 'opaque-one', riotId: 'Self#TEST', region: 'EU', ranks: [], connected: false}
    const state = {accounts: [account], openedAccountId: account.id} as unknown as AppState
    for (const command of ['add_account', 'import_session', 'connect_riot_client', 'connect_riot_qr_image']) expect(approvedProfileAccount(command, state)).toBe(account)
    expect(approvedProfileAccount('activity', state)).toBeUndefined()
    expect(approvedProfileAccount('connect_riot_client', {...state, openedAccountId: 'missing'})).toBeUndefined()
  })
})
