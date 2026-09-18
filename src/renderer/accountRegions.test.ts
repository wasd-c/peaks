import {afterEach, describe, expect, it} from 'vitest'
import {accountRegionForGame, accountRegionLabel, accountRegionLabels} from './accountRegions'
import {i18n} from './i18n'
import type {Account} from './types'

const account: Account = {id: 'demo', riotId: 'Player#EUW', region: 'GLOBAL', ranks: []}
afterEach(() => { void i18n.changeLanguage('en') })

describe('account regions', () => {
  it('keeps legacy League regions out of VALORANT routing', () => {
    const legacy = {...account, region: 'EUW'}
    expect(accountRegionForGame(legacy, 'League of Legends')).toBe('EUW')
    expect(accountRegionForGame(legacy, 'Teamfight Tactics')).toBe('EUW')
    expect(accountRegionForGame(legacy, 'VALORANT')).toBeUndefined()
    expect(accountRegionLabel(legacy)).toBe('LoL/TFT: EUW')
  })
  it('labels and routes independently detected regions by game', () => {
    const detected = {...account, leagueRegion: 'EUW', valorantRegion: 'EU'}
    expect(accountRegionLabels(detected)).toEqual(['LoL/TFT: EUW', 'VALORANT: EU'])
    expect(accountRegionForGame(detected, 'VALORANT')).toBe('EU')
    expect(accountRegionLabel({...account, valorantRegion: 'KR'})).toBe('VALORANT: KR')
  })
  it('localizes unknown regions without guessing from a Riot tag', async () => {
    await i18n.changeLanguage('fr')
    expect(accountRegionLabel(account)).toBe('Région non détectée')
    expect(accountRegionForGame(account, 'League of Legends')).toBeUndefined()
    expect(accountRegionForGame(account, 'VALORANT')).toBeUndefined()
  })
  it('ignores unsupported values and cross-game platform labels', () => {
    const invalid = {...account, leagueRegion: 'EU', valorantRegion: 'EUW'}
    expect(accountRegionLabel(invalid)).toBe('Region not detected')
    expect(accountRegionForGame({...account, valorantRegion: 'eu.attacker.invalid'}, 'VALORANT')).toBeUndefined()
  })
})
