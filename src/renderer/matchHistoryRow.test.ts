import {describe, expect, it} from 'vitest'
import {matchHistoryRow} from './matchHistoryRow'
import type {Match, MatchPlayer} from './types'

const owner: MatchPlayer = {name: 'Owner#TEST', self: true, agent: 'Jett', rank: 'Ascendant 2', rankTier: 22, currentRank: 'Immortal 3', currentRankTier: 26, stats: {kills: 18, deaths: 12, assists: 3}}
const visitor: MatchPlayer = {name: 'Visitor#TEST', agent: 'Omen', rank: 'Diamond 3', rankTier: 20, stats: {kills: 16, deaths: 15, assists: 4}}
const valorant = (extra: Partial<Match> = {}): Match => ({game: 'VALORANT', result: 'Win', mode: 'Competitive', score: '13-8', agent: 'Jett', delta: '+21 RR', teams: [
  {name: 'Red', won: true, score: 13, players: [owner]}, {name: 'Blue', won: false, score: 8, players: [visitor]},
], ...extra})
const league = (mode = '420', stats: MatchPlayer['stats'] = {kills: 8, deaths: 2, assists: 11}): Match => ({game: 'League of Legends', mode, result: 'Win', score: '32-21', delta: '+24 LP', teams: [{name: 'Blue', won: true, players: [{...owner, agent: '103', rank: 'Gold IV', stats}]}]})
const tft = (placement = 2, extra: Partial<Match> = {}): Match => ({game: 'Teamfight Tactics', mode: '1100', result: 'Top 4', delta: '+30 LP', agent: 'TFT_Pengu', teams: [{name: 'Lobby', players: [{...owner, agent: 'TFT_Pengu', rank: 'Emerald II', stats: {placement}}]}], ...extra})

describe('account match history rows', () => {
  it('uses historical rank, exact team rounds, and a bundled agent portrait', () => {
    const row = matchHistoryRow(valorant(), 'Owner#TEST')
    expect(row).toMatchObject({character: {name: 'Jett'}, result: 'Victory', score: '13-8', rank: 'Ascendant 2', rankTier: 22, delta: 21, deltaUnit: 'RR'})
    expect(row.character?.image).toBeTruthy()
    expect(row.rank).not.toBe(owner.currentRank)
  })

  it('changes result, rounds, portrait and historical rank to the clicked visitor without copying owner RR', () => {
    const row = matchHistoryRow(valorant(), ' visitor#test ')
    expect(row).toMatchObject({character: {name: 'Omen'}, result: 'Defeat', score: '8-13', rank: 'Diamond 3', rankTier: 20})
    expect(row.delta).toBeUndefined()
    expect(row.deltaUnit).toBeUndefined()
    expect(matchHistoryRow(valorant(), 'Absent#TEST')).toEqual({result: 'Unknown'})
  })

  it('does not select ambiguous or hidden players or use a mismatched self marker', () => {
    const hidden = valorant({teams: [{name: 'Red', players: [{...owner, hidden: true}]}]})
    expect(matchHistoryRow(hidden, owner.name)).toEqual({result: 'Unknown'})
    const ambiguous = valorant({teams: [{name: 'Red', players: [owner, {...owner, self: false}]}]})
    expect(matchHistoryRow(ambiguous, owner.name)).toEqual({result: 'Unknown'})
    const conflictingSelves = valorant({teams: [{name: 'Red', won: true, score: 13, players: [owner]}, {name: 'Blue', won: false, score: 8, players: [{...visitor, self: true}]}]})
    expect(matchHistoryRow(conflictingSelves, visitor.name)).toMatchObject({character: {name: 'Omen'}, result: 'Defeat'})
    expect(matchHistoryRow(conflictingSelves, visitor.name).delta).toBeUndefined()
  })

  it('shows League K/D/A rather than team kills and resolves numeric champion IDs', () => {
    const row = matchHistoryRow(league(), owner.name)
    expect(row).toMatchObject({character: {name: 'Ahri'}, result: 'Victory', score: '8/2/11', rank: 'Gold IV', delta: 24, deltaUnit: 'LP'})
    expect(row.rankTier).toBeUndefined()
    expect(matchHistoryRow(league('420', {kills: 0, deaths: 0, assists: 0}), owner.name).score).toBe('0/0/0')
    expect(matchHistoryRow(league('420', {kills: 8, deaths: 2}), owner.name).score).toBeUndefined()
  })

  it('does not substitute overall stats, performance strings, or current rank for missing match evidence', () => {
    const game = league()
    const player = game.teams![0].players[0]
    player.stats = undefined
    player.overallStats = {kills: 999, deaths: 99, assists: 999}
    player.rank = undefined
    game.performance = '9/1/20'
    const row = matchHistoryRow(game, owner.name)
    expect(row.score).toBeUndefined()
    expect(row.rank).toBeUndefined()
    expect(row.rankTier).toBeUndefined()
  })

  it('represents TFT by placement only and leaves ambiguous Double Up outcomes unknown', () => {
    expect(matchHistoryRow(tft(), owner.name)).toMatchObject({placement: 2, result: 'Victory', rank: 'Emerald II', delta: 30, deltaUnit: 'LP'})
    expect(matchHistoryRow(tft(5), owner.name)).toMatchObject({placement: 5, result: 'Defeat'})
    const double = matchHistoryRow(tft(3, {mode: '1160', teamMode: 'duos'}), owner.name)
    expect(double).toMatchObject({placement: 3, result: 'Unknown', delta: 30})
    expect(double.character).toBeUndefined()
    expect(double.score).toBeUndefined()
    expect(matchHistoryRow(tft(5, {mode: '1160', teamMode: 'duos'}), owner.name)).toMatchObject({placement: 5, result: 'Defeat'})
    expect(matchHistoryRow(tft(0), owner.name).placement).toBeUndefined()
  })

  it.each([
    valorant({mode: 'unrated'}), valorant({mode: 'premier'}), valorant({mode: undefined}),
    league('400'), league('450'), league('Ranked'), tft(2, {mode: '1090'}), tft(2, {mode: '1130'}),
  ])('shows neither historical ranks nor RR/LP outside strict ranked modes: $game $mode', game => {
    const row = matchHistoryRow(game, owner.name)
    expect(row.rank).toBeUndefined()
    expect(row.rankTier).toBeUndefined()
    expect(row.delta).toBeUndefined()
    expect(row.deltaUnit).toBeUndefined()
  })

  it.each(['440', 'Ranked Solo', 'Ranked solo / duo', 'Ranked flex', 'RANKED_SOLO_5x5', 'RANKED_FLEX_SR'])('accepts only explicitly recognized League ranked mode %s', mode => {
    expect(matchHistoryRow(league(mode), owner.name).delta).toBe(24)
  })

  it('preserves real zero rewards, rejects wrong units and never creates rewards from results', () => {
    expect(matchHistoryRow(valorant({delta: '0 RR'}), owner.name)).toMatchObject({delta: 0, deltaUnit: 'RR'})
    expect(matchHistoryRow(valorant({delta: '−18 RR'}), owner.name).delta).toBe(-18)
    for (const delta of [undefined, '+24 LP', 'won 24 RR', '24.5 RR', 'Infinity', '1001 RR']) {
      expect(matchHistoryRow(valorant({delta}), owner.name).delta).toBeUndefined()
    }
  })

  it('keeps actual team draw scores and avoids treating free-for-all kills as rounds', () => {
    const draw = valorant({result: 'Draw', teams: [{name: 'Red', score: '14', won: false, players: [owner]}, {name: 'Blue', score: '14', won: false, players: [visitor]}]})
    expect(matchHistoryRow(draw, owner.name)).toMatchObject({result: 'Draw', score: '14-14'})
    expect(matchHistoryRow(valorant({mode: 'Deathmatch', freeForAll: true}), owner.name).score).toBeUndefined()
    expect(matchHistoryRow(valorant({mode: 'Competitive', freeForAll: true}), owner.name).delta).toBeUndefined()
  })

  it('allows explicit owner summaries only when no target identity was requested', () => {
    const game = valorant({teams: undefined})
    expect(matchHistoryRow(game)).toMatchObject({result: 'Victory', score: '13-8', character: {name: 'Jett'}, delta: 21})
    expect(matchHistoryRow(game, 'Visitor#TEST')).toEqual({result: 'Unknown'})
    expect(matchHistoryRow(tft(2, {teams: undefined, score: '#3'}))).toMatchObject({placement: 3, result: 'Victory'})
  })
})
