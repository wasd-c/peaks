import {describe, expect, it} from 'vitest'
import {analyzeActivity, connectionStreak, dayKey, emptyActivity, rankDelta, rankPoints, recentGameMix} from './activityAnalytics'
import {profilePlayer} from './accountProfile'
import type {Game, Match} from './types'

const timestamp = (value: string) => new Date(value).getTime()
const now = timestamp('2026-09-20T12:00:00')
const match = (id: string, at: string, seconds?: number, game: Game = 'VALORANT'): Match => ({id, game, result: 'Win', playedAtTimestamp: timestamp(at), durationSeconds: seconds})

describe('accumulated Riot activity', () => {
  it('deduplicates per game, rejects future/undated matches and never invents duration or logins', () => {
    const one = match('one', '2026-09-19T10:00:00', 1800)
    const unknown = match('unknown', '2026-09-19T12:00:00')
    const stats = analyzeActivity(emptyActivity([one, one, {...one, game: 'League of Legends'}, unknown, {...one, id: 'undated', playedAtTimestamp: undefined}, match('future', '2026-10-01', 1800)]), now)
    expect(stats.matches).toHaveLength(3)
    expect(stats.durationCount).toBe(2)
    expect(stats.seconds).toBe(3600)
    expect(stats.streak).toBe(0)
    expect(stats.gamesPlayed).toBe(2)
  })
  it('splits midnight playtime into local calendar days and hours without double-counting total playtime', () => {
    const stats = analyzeActivity(emptyActivity([match('night', '2026-09-18T23:30:00', 3600)]), now)
    expect(stats.seconds).toBe(3600)
    expect(stats.days.get('2026-09-18')?.seconds).toBe(1800)
    expect(stats.days.get('2026-09-19')?.seconds).toBe(1800)
    expect(stats.hours[4][23]).toBe(1800)
    expect(stats.hours[5][0]).toBe(1800)
    expect(stats.days.get('2026-09-19')?.matches[0].id).toBe('night')
    expect(stats.matches).toHaveLength(1)
  })
  it('groups sessions at the documented 45 minute gap, with independent game switching', () => {
    const stats = analyzeActivity(emptyActivity([
      match('one', '2026-09-19T10:00:00', 1800),
      match('two', '2026-09-19T11:15:00', 1800, 'League of Legends'),
      match('three', '2026-09-19T12:30:01', 3600, 'Teamfight Tactics'),
    ]), now)
    expect(stats.sessions).toHaveLength(2)
    expect(stats.longest).toBe(105 * 60)
    expect(stats.average).toBe(82.5 * 60)
    expect(stats.switching[0][1]).toBe(1)
    expect(stats.switching[1][2]).toBe(0)
    expect(stats.histogram.reduce((sum, value) => sum + value, 0)).toBe(2)
  })
  it('keeps silent weeks and clips recent balance to the exact time window', () => {
    const matches = [match('old', '2026-09-01T10:00:00', 1800), match('edge', '2026-09-13T11:30:00', 3600)]
    const stats = analyzeActivity(emptyActivity(matches), now)
    expect(stats.weeks.get('2026-09-14')?.VALORANT).toBe(0)
    expect(recentGameMix(matches, 7, now).VALORANT).toBe(1800)
  })
  it('counts observed connection days only, tolerating an unfinished current day', () => {
    expect(dayKey(now)).toBe('2026-09-20')
    expect(connectionStreak(['2026-09-18', '2026-09-19', '2026-09-19'], now)).toBe(2)
    expect(connectionStreak(['2026-09-18'], now)).toBe(0)
    expect(connectionStreak(['2026-09-18', '2026-09-19', '2026-09-20'], now)).toBe(3)
  })
  it('reads explicit zero/signed rewards and accounts for rank promotions', () => {
    expect(rankDelta('+21 RR')).toBe(21)
    expect(rankDelta('-15 LP')).toBe(-15)
    expect(rankDelta('0')).toBe(0)
    expect(rankDelta('Win')).toBeUndefined()
    expect(rankDelta('45%')).toBeUndefined()
    const before = rankPoints({game: 'League of Legends', tier: 'Gold', division: 'II', rating: 90})!
    const after = rankPoints({game: 'League of Legends', tier: 'Gold I', rating: 15})!
    expect(after - before).toBe(25)
    expect(rankPoints({game: 'VALORANT', tier: 'Ascendant 3', rating: 99})).toBe(2099)
    expect(rankPoints({game: 'VALORANT', tier: 'Immortal 1', rating: 15})).toBe(2115)
    expect(rankPoints({game: 'Teamfight Tactics', tier: 'Unranked'})).toBeUndefined()
  })
  it('uses the clicked player when a report also marks the owner as self', () => {
    const owner = {name: 'Owner#TEST', self: true, stats: {kills: 20}}
    const target = {name: 'Target#TEST', stats: {kills: 5}}
    expect(profilePlayer({...match('one', '2026-09-19', 1200), teams: [{name: 'Team', players: [owner, target]}]}, 'Target#TEST')).toBe(target)
  })
})
