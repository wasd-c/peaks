import {describe, expect, it} from 'vitest'
import {accountGameIcon, accountIconOptions, findAccountIcon, resolveAccountIcon} from './accountIcons'
import type {Account} from './types'

const base: Account = {id: 'account-one', riotId: 'Player#TEST', region: 'EUW', ranks: []}

describe('account character artwork', () => {
  it('bundles both complete character catalogs and game icons without runtime URLs', () => {
    expect(accountIconOptions('League of Legends').length).toBeGreaterThan(170)
    expect(accountIconOptions('VALORANT').length).toBeGreaterThan(25)
    for (const game of ['VALORANT', 'League of Legends'] as const) {
      expect(accountGameIcon(game)).not.toMatch(/^https?:/)
      const options = accountIconOptions(game)
      expect(new Set(options.map(option => option.characterId)).size).toBe(options.length)
      for (const option of options) {
        expect(option.image).toBeTruthy()
        expect(option.image).not.toMatch(/^https?:/)
      }
    }
  })

  it('resolves client names, stable IDs and numeric League IDs', () => {
    const ahri = findAccountIcon({game: 'League of Legends', characterId: '103'})
    expect(ahri?.characterId).toBe('Ahri')
    expect(findAccountIcon({game: 'League of Legends', characterId: '아리'})).toEqual(ahri)
    const omen = findAccountIcon({game: 'VALORANT', characterId: 'omen'})
    expect(omen?.name).toBe('Omen')
    expect(findAccountIcon({game: 'VALORANT', characterId: omen!.characterId})).toEqual(omen)
    expect(findAccountIcon({game: 'VALORANT', characterId: 'https://example.invalid/avatar'})).toBeUndefined()
  })

  it('keeps manual choice even when a newer match uses a different character or game', () => {
    expect(resolveAccountIcon({...base,
      accountIcon: {game: 'League of Legends', characterId: 'Ahri'},
      matches: [{game: 'VALORANT', result: 'Win', agent: 'Omen'}],
    })?.name).toBe('Ahri')
  })

  it('uses the actual self character in the newest supported match and ignores TFT rows', () => {
    expect(resolveAccountIcon({...base, matches: [
      {game: 'Teamfight Tactics', result: 'Top 4'},
      {game: 'League of Legends', result: 'Win', teams: [{name: 'Blue', players: [
        {name: 'Teammate#TEST', agent: 'Garen'},
        {name: 'Player#TEST', agent: 'Ahri', self: true},
      ]}]},
      {game: 'VALORANT', result: 'Win', agent: 'Omen'},
    ]})?.name).toBe('Ahri')
  })

  it('supports exact account identity when a history provider omits the self flag', () => {
    expect(resolveAccountIcon({...base, matches: [
      {game: 'VALORANT', result: 'Win', teams: [{name: 'Red', players: [
        {name: 'Teammate#TEST', agent: 'Gekko'},
        {name: 'player#test', agent: 'Waylay'},
      ]}]},
    ]})?.name).toBe('Waylay')
  })

  it('compares real cross-game timestamps without changing the account history order', () => {
    const account: Account = {...base, matches: [
      {game: 'VALORANT', result: 'Win', agent: 'Omen', playedAtTimestamp: 1_770_000_000_000},
      {game: 'VALORANT', result: 'Win', agent: 'Gekko'},
      {game: 'League of Legends', result: 'Win', agent: 'Ahri', playedAtTimestamp: 1_770_000_060_000},
    ]}
    const original = JSON.stringify(account)
    expect(resolveAccountIcon(account)?.name).toBe('Ahri')
    expect(JSON.stringify(account)).toBe(original)
  })

  it('puts unknown legacy dates behind dated rows and keeps unknown latest characters neutral', () => {
    expect(resolveAccountIcon({...base, matches: [
      {game: 'VALORANT', result: 'Win', agent: 'Omen', playedAt: 'just now'},
      {game: 'League of Legends', result: 'Win', playedAtTimestamp: 1_770_000_060_000},
    ]})).toBeUndefined()
  })

  it('never substitutes an arbitrary teammate, older character or remote avatar', () => {
    expect(resolveAccountIcon({...base, matches: [
      {game: 'VALORANT', result: 'Win', teams: [{name: 'Blue', players: [
        {name: 'Teammate#TEST', agent: 'Garen'},
        {name: 'Player#TEST', agent: 'Unknown', self: true},
      ]}]},
      {game: 'VALORANT', result: 'Win', agent: 'Omen'},
    ]})).toBeUndefined()
    expect(resolveAccountIcon(base)).toBeUndefined()
    expect(resolveAccountIcon({...base, matches: [{game: 'Teamfight Tactics', result: 'Win'}]})).toBeUndefined()
  })
})
