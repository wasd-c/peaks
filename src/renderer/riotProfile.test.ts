import {describe, expect, it} from 'vitest'
import {championArtwork, tftAssetLabel, tftSpriteStyle} from './profileAssets'
import {favoriteCharacter, leagueSummary, tftSummary} from './riotProfile'
import type {Account, Match, PlayerStats} from './types'

const league = (agent: string, stats: PlayerStats, durationSeconds?: number, result = 'Win'): Match => ({game: 'League of Legends', result, durationSeconds, teams: [{name: 'Team', players: [{name: 'Owned#TEST', agent, self: true, stats}]}]})
const tft = (placement: number, duos = false): Match => {
  const players = [{name: 'Owned#TEST', self: true, stats: {placement}}]
  if (duos) {
    const remaining = [1, 1, 2, 2, 3, 3, 4, 4]
    remaining.splice(remaining.indexOf(placement), 1)
    players.push(...remaining.map((value, index) => ({name: `Other${index}#TEST`, self: false, stats: {placement: value}})))
  }
  return {game: 'Teamfight Tactics', result: 'Top 4', teamMode: duos ? 'duos' : undefined, teams: [{name: 'Lobby', players}]}
}

describe('Riot profiles', () => {
  it('chooses the most played recognized character separately for each game', () => {
    const account = {riotId: 'Owned#TEST', matches: [league('103', {}), league('Ahri', {}), league('Jinx', {}), {game: 'VALORANT', result: 'Win', agent: 'Omen'}]} as Account
    expect(favoriteCharacter(account, 'League of Legends')).toEqual({id: 'Ahri', name: 'Ahri', count: 2})
    expect(favoriteCharacter(account, 'VALORANT')?.name).toBe('Omen')
    expect(favoriteCharacter(account, 'Teamfight Tactics')).toBeUndefined()
    expect(championArtwork('103')).toContain('Ahri.webp')
  })
  it('uses weighted League rates and excludes missing-duration evidence', () => {
    const stats = leagueSummary([league('Ahri', {kills: 10, deaths: 2, assists: 6, minions: 100}, 600), league('Ahri', {kills: 0, deaths: 8, assists: 4, minions: 150}, 1800, 'Defeat'), league('Ahri', {minions: 99999})], 'Owned#TEST')
    expect(stats.kda).toBe(2)
    expect(stats.csPerMinute).toBe(6.25)
    expect(stats.detailed).toBe(2)
    expect(stats.winRate).toBeCloseTo(200 / 3)
    expect(stats.damagePerMinute).toBeUndefined()
    expect(stats.killParticipation).toBeUndefined()
    expect(stats.vision).toBeUndefined()
  })
  it('does not mix Double Up ranks with eight-player placements', () => {
    const matches = [tft(1), tft(5), tft(2, true), tft(3, true), tft(9)]
    expect(tftSummary(matches, 'Owned#TEST')).toMatchObject({detailed: 2, average: 3, topRate: 50, winRate: 50})
    expect(tftSummary(matches, 'Owned#TEST', true)).toMatchObject({detailed: 2, average: 2.5, topRate: 50, winRate: 0})
    expect(tftSummary([], 'Owned#TEST').average).toBeUndefined()
  })
  it('resolves bundled TFT art by exact set identifiers and keeps unknown sets explicit', () => {
    expect(tftAssetLabel('champion', 'TFT17_Briar')).toBe('Briar')
    expect(tftSpriteStyle('champion', 'TFT17_Briar')?.backgroundImage).toContain('tft-champion')
    expect(tftAssetLabel('champion', 'TFT999_Future')).toBe('TFT999_Future')
    expect(tftSpriteStyle('champion', 'TFT999_Future')).toBeUndefined()
  })
})
