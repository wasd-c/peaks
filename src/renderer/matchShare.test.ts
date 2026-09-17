import {describe, expect, it} from 'vitest'
import {matchShareCaption, matchShareFilename, matchShareSummary} from './matchShare'
import type {Match, MatchPlayer} from './types'

const decoratedPlayer: MatchPlayer = {
  name: 'Selected#EUW', riotId: 'Selected#EUW', self: true,
  stats: {
    kills: 24, deaths: 12, assists: 12, roundsPlayed: 12,
    roundKills: [5, 5, 5, 5, 4, 0, 0, 0, 0, 0, 0, 0],
    headshots: 20, bodyshots: 20, legshots: 0,
  },
  overallStats: {
    kills: 120, deaths: 60, roundsPlayed: 100, matchesPlayed: 5, wins: 4,
    headshots: 90, bodyshots: 90, legshots: 0,
  },
}

const decoratedMatch: Match = {
  game: 'VALORANT', result: 'Win', playedAt: '42 minutes ago', duration: '38 min',
  teams: [{name: 'Team', players: [decoratedPlayer]}],
}

const match: Match = {
  game: 'VALORANT',
  result: 'Win',
  map: 'Ascent',
  score: '13 : 8',
  teams: [{name: 'Your team', players: [
    {name: 'You#EUW', riotId: 'You#EUW', self: true, stats: {kills: 22, deaths: 12, assists: 6, combatScore: 5250, damage: 3150, roundsPlayed: 21}},
    {name: 'Hidden player', riotId: 'Private#ID', hidden: true, stats: {kills: 30}},
  ]}],
}

describe('public match share summary', () => {
  it('exports only selected player performance with per-round values', () => {
    const summary = matchShareSummary(match, {riotId: 'you#euw'})
    expect(summary).toMatchObject({playerName: 'You#EUW', kda: '22 / 12 / 6', combatScore: '250', damagePerRound: '150'})
    expect(JSON.stringify(summary)).not.toContain('Private#ID')
    expect(summary).not.toHaveProperty('teams')
  })

  it('never exposes a hidden selected identity or borrows another player stats', () => {
    expect(matchShareSummary(match, {riotId: 'Private#ID'}).playerName).toBeUndefined()
    expect(matchShareSummary(match, {riotId: 'Missing#ID'}).kda).toBeUndefined()
    const hiddenSelf = {...match, teams: [{name: 'Team', players: [{name: 'Hidden', riotId: 'Secret#ID', self: true, hidden: true}]}]}
    expect(matchShareSummary(hiddenSelf).playerName).toBeUndefined()
  })

  it('keeps missing statistics missing and makes a safe filename', () => {
    const summary = matchShareSummary({game: 'VALORANT', result: 'Loss', map: '/Game/Maps/Ascent', teams: [{name: 'Team', players: [{name: 'You', self: true, stats: {kills: 8}}]}]})
    expect(summary.kda).toBe('8 / — / —')
    expect(summary.damagePerRound).toBeUndefined()
    expect(summary.combatScore).toBeUndefined()
    expect(matchShareFilename(summary)).toBe('peaks-valorant-game-maps-ascent-loss.png')
    expect(matchShareCaption(summary, 'Ascent')).toContain('made with Peaks')
  })

  it('exports earned labels only, prioritizes match evidence, deduplicates and caps at four', () => {
    const summary = matchShareSummary(decoratedMatch)
    expect(summary.tags).toEqual([
      {label: 'Lobby eviction', source: 'match'},
      {label: 'Headshot merchant', source: 'match'},
      {label: 'Assist department', source: 'match'},
      {label: 'Certified problem', source: 'history'},
    ])
    summary.tags.forEach(tag => expect(Object.keys(tag).sort()).toEqual(['label', 'source']))
    expect(summary.tags.every(tag => tag.label.length <= 64)).toBe(true)
  })

  it('takes tags only from the selected owner and keeps streamer aliases intact', () => {
    const selected: MatchPlayer = {name: 'Other#EUW', riotId: 'Other#EUW', stats: {kills: 2}}
    const roster = {...decoratedMatch, teams: [{name: 'Team', players: [decoratedPlayer, selected]}]}
    const summary = matchShareSummary(roster, {riotId: 'Other#EUW'}, () => 'Player 02')
    expect(summary.playerName).toBe('Player 02')
    expect(summary.tags).toEqual([])
    expect(JSON.stringify(summary)).not.toContain('Selected#EUW')
    const aliasedOwner = matchShareSummary(roster, {riotId: 'Selected#EUW'}, () => 'Player 01')
    expect(aliasedOwner.playerName).toBe('Player 01')
    expect(aliasedOwner.tags).toEqual(matchShareSummary(decoratedMatch).tags)
  })

  it('never exports tags for hidden, missing or unsupported owners', () => {
    const hidden = {...decoratedMatch, teams: [{name: 'Team', players: [{...decoratedPlayer, hidden: true}]}]}
    expect(matchShareSummary(hidden).tags).toEqual([])
    expect(matchShareSummary(hidden, {riotId: 'Selected#EUW'}).tags).toEqual([])
    expect(matchShareSummary(decoratedMatch, {riotId: 'Missing#EUW'}).tags).toEqual([])
    expect(matchShareSummary({...decoratedMatch, game: 'League of Legends'}).tags).toEqual([])
  })

  it('never turns insufficient historical evidence into a tag', () => {
    const player = {...decoratedPlayer, stats: undefined, overallStats: {matchesPlayed: 1, wins: 1, kills: 100}}
    const summary = matchShareSummary({...decoratedMatch, teams: [{name: 'Team', players: [player]}]})
    expect(summary.tags).toEqual([])
  })

  it('omits relative and calendar metadata while keeping actual match duration', () => {
    const summary = matchShareSummary(decoratedMatch)
    expect(summary).not.toHaveProperty('playedAt')
    expect(JSON.stringify(summary)).not.toContain('42 minutes ago')
    expect(matchShareCaption(summary, 'Ascent')).not.toContain('42 minutes ago')
    expect(summary.duration).toBe('38 min')
  })
})
