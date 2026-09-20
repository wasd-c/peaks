import {describe, expect, it} from 'vitest'
import {tftRecentResults} from './tftRecentResults'
import {matchHistoryRow} from './matchHistoryRow'
import {tftSummary} from './riotProfile'
import type {Match} from './types'

const owner = 'Owner#TEST'
const match = (id: number, placement?: number, extra: Partial<Match> = {}): Match => ({
  id: `game-${id}`, game: 'Teamfight Tactics', result: 'Unknown', playedAtTimestamp: 1_735_689_600_000 + id * 60_000,
  teams: [{name: 'Lobby', players: [{name: owner, self: true, stats: {placement}}]}], ...extra,
})
const duoMatch = (id: number, placement: number, scale: 'teams' | 'individuals' = 'teams'): Match => {
  const game = match(id, placement, {mode: '1160', teamMode: 'duos'})
  const remaining = scale === 'teams' ? [1, 1, 2, 2, 3, 3, 4, 4] : [1, 2, 3, 4, 5, 6, 7, 8]
  remaining.splice(remaining.indexOf(placement), 1)
  game.teams![0].players.push(...remaining.map((value, index) => ({name: `Other${index}#TEST`, stats: {placement: value}})))
  return game
}

describe('TFT recent placements and current streak', () => {
  it('uses the latest 20 dated unique games while keeping a longer current streak', () => {
    const games = Array.from({length: 23}, (_, index) => match(index, index % 4 + 1))
    const result = tftRecentResults([...games, games[2], {game: 'VALORANT', result: 'Win'}], owner)
    expect(result.rows).toHaveLength(20)
    expect(result.rows[0].match.id).toBe('game-22')
    expect(result.rows.at(-1)?.match.id).toBe('game-3')
    expect(result.streak).toBe(23)
    expect(games[0].id).toBe('game-0')
  })

  it('includes all queues in the latest twenty instead of dropping five Double Up games', () => {
    const games = Array.from({length: 20}, (_, index) => index % 4 === 0 ? duoMatch(index, 2) : match(index, 4))
    const result = tftRecentResults(games, owner)
    expect(result.rows).toHaveLength(20)
    expect(result.streak).toBe(20)
    expect(tftRecentResults(games, owner, false).rows).toHaveLength(15)
    expect(tftRecentResults(games, owner, true).rows).toHaveLength(5)
  })

  it('counts consecutive top four finishes and restarts after a bottom four finish', () => {
    expect(tftRecentResults([match(1, 2), match(2, 5), match(3, 4), match(4, 2)], owner).streak).toBe(2)
    expect(tftRecentResults([match(1, 8), match(2, 4)], owner).streak).toBe(1)
  })

  it('returns a signed consecutive loss streak', () => {
    const result = tftRecentResults([match(1, 1), match(2, 5), match(3, 8), match(4, 7), match(5, 6)], owner)
    expect(result.streak).toBe(-4)
  })

  it('never joins a streak across missing or invalid placements', () => {
    expect(tftRecentResults([match(1, 1), match(2), match(3, 2), match(4, 4)], owner).streak).toBe(2)
    for (const placement of [undefined, 0, 9, 3.5, Number.NaN]) {
      const result = tftRecentResults([match(1, 1), match(2, placement)], owner)
      expect(result.streak).toBeUndefined()
      expect(result.rows[0].placement).toBeUndefined()
    }
  })

  it('does not claim a current streak when a game cannot be ordered by its timestamp', () => {
    const result = tftRecentResults([match(1, 1), match(2, 2, {playedAtTimestamp: undefined})], owner)
    expect(result.streak).toBeUndefined()
    expect(result.rows.map(row => row.match.id)).toEqual(['game-1'])
    const future = tftRecentResults([match(1, 1), match(2, 1, {playedAtTimestamp: Date.now() + 86_400_000})], owner)
    expect(future.streak).toBeUndefined()
    expect(future.rows.map(row => row.match.id)).toEqual(['game-1'])
  })

  it('keeps Double Up separate and uses its top two cut-off', () => {
    const games = [duoMatch(1, 1), duoMatch(2, 3), duoMatch(3, 4), match(4, 1)]
    const result = tftRecentResults(games, owner, true)
    expect(result.streak).toBe(-2)
    expect(result.rows[0].positivePlacement).toBe(2)
    expect(result.rows).toHaveLength(3)
    expect(tftRecentResults(games, owner).streak).toBe(1)
  })

  it('classifies each game using its proven placement scale without converting raw places', () => {
    const teamScale = tftRecentResults([match(1, 4), duoMatch(2, 2), duoMatch(3, 3)], owner)
    expect(teamScale.streak).toBe(-1)
    const individualScale = tftRecentResults([match(1, 4), duoMatch(2, 3, 'individuals'), duoMatch(3, 4, 'individuals')], owner)
    expect(individualScale.streak).toBe(3)
    expect(individualScale.rows[0].positivePlacement).toBe(4)
    expect(individualScale.rows.map(row => row.placement)).toEqual([4, 3, 4])
    const loss = tftRecentResults([duoMatch(1, 4, 'individuals'), duoMatch(2, 7, 'individuals')], owner)
    expect(loss.streak).toBe(-1)
    expect(loss.rows[0].placement).toBe(7)
  })

  it('does not invent a Double Up streak from an ambiguous partial roster', () => {
    const unknown = match(2, 3, {teamMode: 'duos'})
    const result = tftRecentResults([match(1, 4), unknown], owner)
    expect(result.rows[0].placement).toBe(3)
    expect(result.rows[0].positive).toBeUndefined()
    expect(result.streak).toBeUndefined()
    expect(tftRecentResults([match(1, 4), unknown, match(3, 2)], owner).streak).toBe(1)
  })

  it('keeps Double Up history and summary consistent with both proven roster scales', () => {
    const individualGames = [duoMatch(1, 3, 'individuals'), duoMatch(2, 4, 'individuals'), duoMatch(3, 7, 'individuals')]
    expect(individualGames.map(game => matchHistoryRow(game, owner))).toMatchObject([
      {placement: 3, result: 'Victory'}, {placement: 4, result: 'Victory'}, {placement: 7, result: 'Defeat'},
    ])
    const individualSummary = tftSummary(individualGames, owner, true)
    expect(individualSummary).toMatchObject({detailed: 3, average: 14 / 3, positivePlacement: 4})
    expect(individualSummary.topRate).toBeCloseTo(200 / 3)
    expect(individualSummary.distribution).toHaveLength(8)
    expect(individualSummary.distribution[6]).toEqual({placement: 7, count: 1})

    const teamGames = [duoMatch(4, 2), duoMatch(5, 3)]
    expect(teamGames.map(game => matchHistoryRow(game, owner))).toMatchObject([
      {placement: 2, result: 'Victory'}, {placement: 3, result: 'Defeat'},
    ])
    expect(tftSummary(teamGames, owner, true)).toMatchObject({detailed: 2, average: 2.5, topRate: 50, positivePlacement: 2})
    expect(tftSummary(teamGames, owner, true).distribution).toHaveLength(4)
    const mixed = tftSummary([...individualGames, ...teamGames], owner, true)
    expect(mixed).toMatchObject({detailed: 5, topRate: 60, positivePlacement: undefined})
    expect(mixed.distribution).toHaveLength(8)
  })

  it('preserves ambiguous raw places without inventing outcomes or depressing proven top rates', () => {
    const unknown = match(2, 3, {teamMode: 'duos', result: 'Defeat'})
    expect(matchHistoryRow(unknown, owner)).toMatchObject({placement: 3, result: 'Unknown'})
    expect(tftSummary([unknown], owner, true)).toMatchObject({detailed: 1, average: 3, topRate: undefined, positivePlacement: undefined})
    expect(tftSummary([unknown, duoMatch(3, 3, 'individuals')], owner, true)).toMatchObject({detailed: 2, topRate: 100, positivePlacement: 4})
  })

  it('uses the selected Riot identity instead of another player in the same report', () => {
    const game = match(1, 8)
    game.teams![0].players.unshift({name: 'Visitor#TEST', stats: {placement: 1}})
    expect(tftRecentResults([game], 'Visitor#TEST').streak).toBe(1)
    expect(tftRecentResults([game], owner).streak).toBe(-1)
  })
})
