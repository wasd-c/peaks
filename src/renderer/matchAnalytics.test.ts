import {describe, expect, it} from 'vitest'
import {historicalPerformanceTags, matchAnalytics, playerPerformanceTags, type MatchAnalyticsStats} from './matchAnalytics'
import type {Match} from './types'

const matchWithStats = (stats: MatchAnalyticsStats): Match => ({
  game: 'VALORANT', result: 'Win',
  teams: [{name: 'Team', players: [{name: 'Owner#EUW', self: true, stats}]}],
})

describe('evidence-based match analytics', () => {
  it('keeps historical tags separate from match evidence and requires a bounded sample', () => {
    const player = {name: 'Player#EU', stats: {roundKills: [3], kills: 3}, overallStats: {
      matchesPlayed: 5, wins: 4, kills: 100, deaths: 60, roundsPlayed: 100, headshots: 90, bodyshots: 150, legshots: 10,
    }}
    expect(historicalPerformanceTags(player, 'VALORANT').map(tag => tag.label)).toEqual(['Headshot merchant', 'Certified problem', 'Win collector'])
    expect(playerPerformanceTags(player, 'VALORANT').map(tag => tag.label)).toEqual(["Three's a crowd"])
    expect(historicalPerformanceTags({...player, overallStats: {kills: 100}}, 'VALORANT')).toEqual([])
    expect(historicalPerformanceTags({...player, hidden: true}, 'VALORANT')).toEqual([])
    expect(historicalPerformanceTags({...player, overallStats: {matchesPlayed: 1, wins: 5}}, 'VALORANT')).toEqual([])
  })
  it('uses landed hits for head/body/feet and omits incomplete distributions', () => {
    const insights = matchAnalytics([
      matchWithStats({headshots: 10, bodyshots: 25, legshots: 5}),
      matchWithStats({headshots: 300}),
    ])
    expect(insights.totalHits).toBe(40)
    expect(insights.hitMatches).toBe(1)
    expect(insights.hitDistribution.map(item => item.percentage)).toEqual([25, 62.5, 12.5])
  })

  it('does not invent multikills from a high total kill count', () => {
    expect(matchAnalytics([matchWithStats({kills: 30})]).tags).toEqual([])
    const result = matchAnalytics([matchWithStats({roundKills: [0, 2, 2, 3, 4, 5]})])
    expect(result.tags).toEqual([{label: 'Lobby eviction', detail: '1 recorded round with 5+ eliminations.'}])
  })

  it('uses only analyzed surrender rounds for events while preserving official ACS rounds', () => {
    const stats = {kills: 14, deaths: 14, assists: 0, roundsPlayed: 12, roundsAnalyzed: 11,
      combatScore: 3909, roundKills: [1, 1, 0, 1, 1, 3, 2, 3, 2, 0, 0],
      weaponUsage: [{weapon: 'Vandal', kills: 13}, {weapon: 'Melee', kills: 1}]}
    const result = matchAnalytics([matchWithStats(stats)])
    expect(result.roundMatches).toBe(1)
    expect(result.tags).toContainEqual({label: "Three's a crowd", detail: '2 recorded rounds with 3 eliminations.'})
    expect(result.tags).toContainEqual({label: 'Lobby landlord', detail: '326 average combat score over 12 rounds.'})
    expect(result.weapons).toContainEqual(expect.objectContaining({weapon: 'Melee', kills: 1}))
    expect(JSON.stringify(result.tags)).not.toMatch(/AFK|inactive|zero.kill/i)
    for (const changed of [
      {...stats, roundsAnalyzed: 10}, {...stats, roundsPlayed: 16}, {...stats, kills: 15},
      {...stats, roundKills: [...stats.roundKills, 0, 0, 0, 0, 0]},
    ]) expect(matchAnalytics([matchWithStats(changed)]).roundMatches).toBe(0)
  })

  it('aggregates actual weapon kills and grounds quiet tags in complete round statistics', () => {
    const result = matchAnalytics([
      matchWithStats({kills: 4, assists: 0, roundsPlayed: 10, weaponUsage: [{weapon: 'Vandal', kills: 3}, {weapon: 'Ghost', kills: 1}]}),
      matchWithStats({weaponUsage: [{weapon: 'vandal', kills: 2}]}),
    ])
    expect(result.weapons[0]).toMatchObject({weapon: 'Vandal', kills: 5})
    expect(result.weapons[0].percentage).toBeCloseTo(83.333)
    expect(result.tags).toEqual([])
    expect(matchAnalytics([matchWithStats({kills: 3, assists: 1, roundsPlayed: 12})]).tags)
      .toContainEqual({label: 'Rough shift', detail: '3 kills and 1 assist across 12 rounds (0.33 combined per round).'})
    expect(matchAnalytics([matchWithStats({kills: 0, roundsPlayed: 20})]).tags).toEqual([])
  })

  it('does not expose hidden players or substitute another player for the requested identity', () => {
    const match = matchWithStats({headshots: 10, bodyshots: 10, legshots: 0})
    expect(matchAnalytics([match], 'other#euw').totalHits).toBe(0)
    match.teams![0].players[0].hidden = true
    expect(matchAnalytics([match]).totalHits).toBe(0)
  })

  it('tags other visible roster players from their own round evidence only', () => {
    const stats: MatchAnalyticsStats = {roundKills: [3], kills: 3}
    const player = {name: 'Opponent#EUW', stats}
    expect(playerPerformanceTags(player, 'VALORANT')).toEqual([{label: "Three's a crowd", detail: '1 recorded round with 3 eliminations.'}])
    expect(playerPerformanceTags({...player, hidden: true}, 'VALORANT')).toEqual([])
    expect(playerPerformanceTags(player, 'League of Legends')).toEqual([])
    expect(playerPerformanceTags({name: 'Unknown', stats: {kills: 25}}, 'VALORANT')).toEqual([])
  })

  it('does not award low-activity tags when the history window is incomplete', () => {
    const quiet = matchWithStats({kills: 0, assists: 0, roundsPlayed: 20})
    expect(matchAnalytics([quiet, matchWithStats({kills: 30})]).tags).toEqual([])
    expect(matchAnalytics([quiet, {game: 'VALORANT', result: 'Win'}]).tags).toEqual([])
  })

  it('rejects partial, malformed and inconsistent event windows as unavailable', () => {
    for (const stats of [
      {roundKills: [3, -1]},
      {roundKills: [3, Number.NaN]},
      {roundKills: [3], roundsPlayed: 20},
      {roundKills: [3], kills: 25},
      {roundKills: []},
      {weaponUsage: [{weapon: 'Vandal', kills: 2}, {weapon: 'Ghost', kills: -1}]},
      {weaponUsage: [{weapon: 'Vandal', kills: 2}], kills: 1},
    ]) {
      const insights = matchAnalytics([matchWithStats(stats)])
      expect(insights.roundMatches).toBe(0)
      expect(insights.weaponMatches).toBe(0)
      expect(insights.tags).toEqual([])
      expect(insights.weapons).toEqual([])
    }
  })

  it('gives sharp banter a visible numerical basis without inferring accuracy or timing', () => {
    const tags = playerPerformanceTags({name: 'Player', stats: {
      kills: 6, deaths: 18, assists: 2, roundsPlayed: 20,
      headshots: 2, bodyshots: 38, legshots: 0,
    }}, 'VALORANT')
    expect(tags.map(tag => tag.label)).toEqual(['Center-mass enjoyer', "Death's bestie"])
    expect(tags[0].detail).toContain('95% body hits')
    expect(tags[1].detail).toContain('0.90 deaths per round')
    expect(JSON.stringify(tags)).not.toMatch(/accuracy|early|AFK|smurf|cheat/i)
  })

  it('requires real sample sizes, complete denominators and valid numbers', () => {
    const small = {name: 'Player', stats: {kills: 3, deaths: 0, roundsPlayed: 2, headshots: 2, bodyshots: 0, legshots: 0}}
    expect(playerPerformanceTags(small, 'VALORANT')).toEqual([])
    for (const stats of [
      {},
      {kills: 0, deaths: 0, assists: 0, roundsPlayed: 0, headshots: 0, bodyshots: 0, legshots: 0},
      {kills: 12, deaths: 0},
      {kills: 12, deaths: Number.NaN, roundsPlayed: 20},
      {assists: 20},
      {combatScore: 6000, damage: 4000},
      {combatScore: 6000, roundsPlayed: -1},
      {headshots: 50, bodyshots: 0},
      {headshots: 50, bodyshots: -1, legshots: 0},
    ]) expect(playerPerformanceTags({name: 'Player', stats}, 'VALORANT')).toEqual([])

    expect(historicalPerformanceTags({name: 'Player', overallStats: {
      matchesPlayed: 2, kills: 80, deaths: 20, roundsPlayed: 40, headshots: 50, bodyshots: 50, legshots: 0,
    }}, 'VALORANT')).toEqual([])
  })

  it('caps each context at three distinct categories and never labels the same impact twice', () => {
    const stats: MatchAnalyticsStats = {
      kills: 25, deaths: 10, assists: 15, roundsPlayed: 20,
      combatScore: 7000, damage: 4000, headshots: 50, bodyshots: 50, legshots: 0,
      roundKills: [5, 4, 3, 2, 2, 2, 2, 2, 2, 1, ...Array<number>(10).fill(0)],
      weaponUsage: [{weapon: 'Vandal', kills: 20}],
    }
    const tags = playerPerformanceTags({name: 'Player', stats}, 'VALORANT')
    expect(tags.map(tag => tag.label)).toEqual(['Lobby eviction', 'Headshot merchant', 'Assist department'])
    expect(tags).toHaveLength(3)
    const impactOnly = playerPerformanceTags({name: 'Player', stats: {
      kills: 25, deaths: 10, assists: 0, roundsPlayed: 20, combatScore: 7000, damage: 4000,
    }}, 'VALORANT')
    expect(impactOnly.map(tag => tag.label)).toEqual(['Certified problem'])
  })

  it('separates weapon preference from a partial weapon list and ignores unknown weapon nicknames', () => {
    const base = {name: 'Player', stats: {kills: 20, weaponUsage: [{weapon: 'Operator', kills: 15}]}}
    expect(playerPerformanceTags(base, 'VALORANT')).toEqual([
      {label: 'Operator landlord', detail: '15 of 20 eliminations used the Operator (75%).'},
    ])
    expect(playerPerformanceTags({...base, stats: {kills: 20, weaponUsage: [{weapon: 'Operator', kills: 5}]}}, 'VALORANT')).toEqual([])
    expect(playerPerformanceTags({...base, stats: {weaponUsage: [{weapon: 'Operator', kills: 15}]}}, 'VALORANT')).toEqual([])
    expect(playerPerformanceTags({...base, stats: {kills: 20, weaponUsage: [{weapon: 'Made-up gun', kills: 15}]}}, 'VALORANT')).toEqual([])
  })

  it('keeps support and low-impact judgments mutually consistent', () => {
    const tags = playerPerformanceTags({name: 'Player', stats: {kills: 2, deaths: 18, assists: 15, roundsPlayed: 20}}, 'VALORANT')
    expect(tags.map(tag => tag.label)).toEqual(['Assist department'])
    const quiet = {kills: 0, assists: 0, roundsPlayed: 20}
    expect(matchAnalytics([
      matchWithStats(quiet), matchWithStats(quiet), matchWithStats({kills: 0, roundsPlayed: 20}),
    ]).tags).toEqual([])
  })

  it('never borrows current stats for historical tags or historical stats for a current tag', () => {
    const stats = {roundKills: [4], kills: 4}
    const overallStats = {matchesPlayed: 5, wins: 0, kills: 100, deaths: 50, roundsPlayed: 100}
    expect(playerPerformanceTags({name: 'Player', overallStats}, 'VALORANT')).toEqual([])
    expect(historicalPerformanceTags({name: 'Player', stats}, 'VALORANT')).toEqual([])
    const player = {name: 'Player', stats, overallStats}
    expect(playerPerformanceTags(player, 'VALORANT').map(tag => tag.label)).toEqual(['Four-piece combo'])
    expect(historicalPerformanceTags(player, 'VALORANT').map(tag => tag.label)).toEqual(['Certified problem', 'Queueing through it'])
    expect(historicalPerformanceTags(player, 'VALORANT').every(tag => tag.detail.endsWith('Across 5 recent games.'))).toBe(true)
  })

  it('handles zero deaths without dividing by zero and never invents a consecutive winning streak', () => {
    const tags = playerPerformanceTags({name: 'Player', stats: {kills: 15, deaths: 0, roundsPlayed: 15}}, 'VALORANT')
    expect(tags).toEqual([{label: 'Certified problem', detail: '15 kills without a recorded death over 15 rounds.'}])
    const historical = historicalPerformanceTags({name: 'Player', overallStats: {matchesPlayed: 5, wins: 4}}, 'VALORANT')
    expect(historical).toEqual([{label: 'Win collector', detail: '4 wins (80% win rate). Across 5 recent games.'}])
    expect(JSON.stringify(historical)).not.toMatch(/streak|consecutive/i)
  })

  it('awards walking orb only for five individually verified deeply negative games', () => {
    const recentKda = [
      {kills: 6, deaths: 10}, {kills: 5, deaths: 15}, {kills: 3, deaths: 12},
      {kills: 0, deaths: 10}, {kills: 8, deaths: 20},
    ]
    const tags = historicalPerformanceTags({name: 'Player', overallStats: {
      matchesPlayed: 5, recentKda, kills: 22, deaths: 67,
      assists: 1, roundsPlayed: 70, combatScore: 28000, damage: 14000,
      headshots: 50, bodyshots: 50, legshots: 0,
    }}, 'VALORANT')
    expect(tags[0].label).toBe('walking orb 🥀')
    expect(tags[0].detail).toContain('Five games, five donations. At this point you’re the enemy team’s ult subscription.')
    expect(tags[0].detail).toContain('0.60 (6/10), 0.33 (5/15), 0.25 (3/12), 0.00 (0/10), 0.40 (8/20)')
    expect(tags[0].detail).toContain('Every game: ≤0.60 K/D and ≥10 deaths.')
    expect(tags.map(tag => tag.label)).not.toEqual(expect.arrayContaining(['Rough shift']))
    expect(tags.some(tag => ['Certified problem', 'Lobby landlord', 'Health inspector', "Death's bestie"].includes(tag.label))).toBe(false)
    expect(tags.length).toBeLessThanOrEqual(3)
  })

  it('does not award walking orb from averages, short windows, a single good game or invalid evidence', () => {
    const fiveBad = Array.from({length: 5}, () => ({kills: 5, deaths: 15}))
    const cases: MatchAnalyticsStats[] = [
      {matchesPlayed: 5, kills: 25, deaths: 75},
      {matchesPlayed: 4, recentKda: fiveBad.slice(0, 4)},
      {matchesPlayed: 5, recentKda: fiveBad.slice(0, 4)},
      {matchesPlayed: 4, recentKda: fiveBad},
      {matchesPlayed: 6, recentKda: fiveBad},
      {matchesPlayed: 5, recentKda: [...fiveBad.slice(0, 4), {kills: 16, deaths: 15}]},
      {matchesPlayed: 5, recentKda: [...fiveBad.slice(0, 4), {kills: 7, deaths: 10}]},
      {matchesPlayed: 5, recentKda: [...fiveBad.slice(0, 4), {kills: 0, deaths: 9}]},
      {matchesPlayed: 5, recentKda: [...fiveBad.slice(0, 4), {kills: 0, deaths: 0}]},
      {matchesPlayed: 5, recentKda: [...fiveBad.slice(0, 4), {kills: -1, deaths: 15}]},
      {matchesPlayed: 5, recentKda: [...fiveBad.slice(0, 4), {kills: 1.5, deaths: 15}]},
      {matchesPlayed: 5, recentKda: [...fiveBad.slice(0, 4), {kills: 1, deaths: Number.NaN}]},
      {matchesPlayed: 5, recentKda: [...fiveBad.slice(0, 4), {kills: 1, deaths: Number.POSITIVE_INFINITY}]},
      {matchesPlayed: 5, recentKda: fiveBad, kills: 26, deaths: 75},
      {matchesPlayed: 5, recentKda: fiveBad, kills: 25, deaths: 74},
      {matchesPlayed: 5, recentKda: fiveBad, kills: Number.NaN},
      {matchesPlayed: 5, recentKda: [null, ...fiveBad.slice(0, 4)]} as unknown as MatchAnalyticsStats,
      {matchesPlayed: 5, recentKda: [{kills: 1}, ...fiveBad.slice(0, 4)]} as unknown as MatchAnalyticsStats,
    ]
    for (const overallStats of cases) {
      expect(historicalPerformanceTags({name: 'Player', overallStats}, 'VALORANT').some(tag => tag.label === 'walking orb 🥀')).toBe(false)
    }
  })

  it('never creates walking orb from current-match evidence or exposes it for hidden players', () => {
    const stats: MatchAnalyticsStats = {
      matchesPlayed: 5, recentKda: Array.from({length: 5}, () => ({kills: 5, deaths: 15})),
      kills: 25, deaths: 75,
    }
    expect(playerPerformanceTags({name: 'Player', stats}, 'VALORANT').some(tag => tag.label === 'walking orb 🥀')).toBe(false)
    expect(historicalPerformanceTags({name: 'Player', stats}, 'VALORANT')).toEqual([])
    expect(historicalPerformanceTags({name: 'Player', overallStats: stats, hidden: true}, 'VALORANT')).toEqual([])
    expect(historicalPerformanceTags({name: 'Player', overallStats: stats}, 'League of Legends')).toEqual([])
    expect(historicalPerformanceTags({name: 'Player', overallStats: stats}, 'VALORANT')[0]?.label).toBe('walking orb 🥀')
  })
})
