import {PROFILE_GAMES} from './riotProfile'
import type {Game, Match, ProfileActivity, Rank} from './types'

export const GAME_COLORS: Record<Game, string> = {'VALORANT': 'var(--color-game-valorant)', 'League of Legends': 'var(--color-game-league)', 'Teamfight Tactics': 'var(--color-game-tft)'}
export const SESSION_GAP_MS = 45 * 60_000
export const dayKey = (time: number | Date) => {
  const date = new Date(time)
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`
}
export const dayDate = (key: string) => new Date(`${key}T00:00:00`)
export const nextDay = (time: number | Date, increment = 1) => {
  const date = new Date(time)
  date.setDate(date.getDate() + increment)
  date.setHours(0, 0, 0, 0)
  return date
}
export const elapsedLabel = (seconds: number) => `${Math.floor(seconds / 3600)}h ${String(Math.floor(seconds % 3600 / 60)).padStart(2, '0')}m`
const blankMix = (): Record<Game, number> => ({'VALORANT': 0, 'League of Legends': 0, 'Teamfight Tactics': 0})
export const emptyActivity = (matches: Match[] = []): ProfileActivity => ({matches, connectionDays: [], identities: [], ranks: []})

export interface ActivityDay {date: string; seconds: number; games: Record<Game, number>; matches: Match[]}
export interface PlaySession {start: number; end: number; seconds: number; matches: Match[]}

export function validActivityMatches(matches: Match[], now = Date.now()) {
  const unique = new Map<string, Match>()
  for (const match of matches) {
    const start = match.playedAtTimestamp
    if (!match.id || !PROFILE_GAMES.includes(match.game) || typeof start !== 'number' || !Number.isFinite(start) || start <= 0 || start > now) continue
    unique.set(`${match.game}:${match.id}`, match)
  }
  return [...unique.values()].sort((a, b) => a.playedAtTimestamp! - b.playedAtTimestamp!)
}
export function matchInterval(match: Match): {start: number; end: number} | undefined {
  const duration = match.durationSeconds
  if (typeof match.playedAtTimestamp !== 'number' || typeof duration !== 'number' || !Number.isFinite(duration) || duration <= 0 || duration > 86_400) return undefined
  return {start: match.playedAtTimestamp, end: match.playedAtTimestamp + duration * 1000}
}
export function connectionStreak(days: string[], now = Date.now()) {
  const observed = new Set(days)
  let cursor = new Date(now), count = 0
  if (!observed.has(dayKey(cursor))) cursor = nextDay(cursor, -1)
  while (observed.has(dayKey(cursor))) { count++; cursor = nextDay(cursor, -1) }
  return count
}

/** All history calculations use timestamps and recorded durations, never relative labels. */
export function analyzeActivity(activity: ProfileActivity, now = Date.now()) {
  const matches = validActivityMatches(activity.matches, now)
  const days = new Map<string, ActivityDay>()
  const mix = blankMix(), hours = Array.from({length: 7}, () => Array<number>(24).fill(0))
  const sessions: PlaySession[] = []
  const switching = PROFILE_GAMES.map(() => [0, 0, 0])
  let durationCount = 0, seconds = 0
  const day = (timestamp: number) => {
    const key = dayKey(timestamp)
    if (!days.has(key)) days.set(key, {date: key, seconds: 0, games: blankMix(), matches: []})
    return days.get(key)!
  }
  for (const match of matches) {
    const interval = matchInterval(match)
    if (!interval) { day(match.playedAtTimestamp!).matches.push(match); continue }
    durationCount++
    seconds += match.durationSeconds!
    mix[match.game] += match.durationSeconds!
    const previous = sessions.at(-1)
    if (previous && interval.start - previous.end <= SESSION_GAP_MS) {
      const last = previous.matches.at(-1)!
      if (last.game !== match.game) switching[PROFILE_GAMES.indexOf(last.game)][PROFILE_GAMES.indexOf(match.game)]++
      previous.end = Math.max(previous.end, interval.end)
      previous.seconds = (previous.end - previous.start) / 1000
      previous.matches.push(match)
    } else sessions.push({...interval, seconds: (interval.end - interval.start) / 1000, matches: [match]})
    let cursor = interval.start
    const touched = new Set<string>()
    while (cursor < interval.end) {
      const date = new Date(cursor), boundary = new Date(cursor)
      boundary.setMinutes(60, 0, 0)
      const end = Math.min(interval.end, boundary.getTime())
      const slice = (end - cursor) / 1000
      const bucket = day(cursor)
      bucket.seconds += slice
      bucket.games[match.game] += slice
      if (!touched.has(bucket.date)) { bucket.matches.push(match); touched.add(bucket.date) }
      hours[(date.getDay() + 6) % 7][date.getHours()] += slice
      cursor = end
    }
  }
  const weeks = new Map<string, Record<Game, number>>()
  for (const entry of days.values()) {
    const date = dayDate(entry.date)
    const monday = dayKey(nextDay(date, -((date.getDay() + 6) % 7)))
    if (!weeks.has(monday)) weeks.set(monday, blankMix())
    for (const game of PROFILE_GAMES) weeks.get(monday)![game] += entry.games[game]
  }
  // Retain silent weeks so the chart's horizontal scale remains chronological.
  if (weeks.size) {
    const last = nextDay(now, -((new Date(now).getDay() + 6) % 7))
    for (let cursor = nextDay(last, -25 * 7); cursor <= last; cursor = nextDay(cursor, 7)) {
      if (!weeks.has(dayKey(cursor))) weeks.set(dayKey(cursor), blankMix())
    }
  }
  const histogram = [0, 0, 0, 0, 0, 0, 0]
  for (const session of sessions) histogram[Math.min(6, Math.floor(session.seconds / 3600))]++
  return {matches, days, mix, seconds, durationCount, activeDays: days.size, gamesPlayed: PROFILE_GAMES.filter(game => matches.some(match => match.game === game)).length,
    hours, sessions, switching, histogram, weeks,
    longest: Math.max(0, ...sessions.map(session => session.seconds)),
    average: sessions.length ? sessions.reduce((sum, session) => sum + session.seconds, 0) / sessions.length : 0,
    streak: connectionStreak(activity.connectionDays, now)}
}

export function recentGameMix(matches: Match[], days: number, now = Date.now()) {
  const mix = blankMix(), start = now - days * 86_400_000
  for (const match of matches) {
    const interval = matchInterval(match)
    if (interval) mix[match.game] += Math.max(0, Math.min(now, interval.end) - Math.max(start, interval.start)) / 1000
  }
  return mix
}

export function rankDelta(value: unknown): number | undefined {
  if (typeof value === 'number') return Number.isFinite(value) ? value : undefined
  if (typeof value !== 'string' || !/^[+-]?\d+(?:\s*(?:RR|LP))?$/i.test(value.trim())) return undefined
  return Number.parseInt(value, 10)
}

/** Rank observations are not invented match rewards. Promotions use the game's ladder. */
export function rankPoints(rank: Rank): number | undefined {
  if (typeof rank.rating !== 'number' || !Number.isFinite(rank.rating)) return undefined
  const valorant = rank.game === 'VALORANT'
  const tiers = valorant ? ['iron', 'bronze', 'silver', 'gold', 'platinum', 'diamond', 'ascendant', 'immortal', 'radiant'] : ['iron', 'bronze', 'silver', 'gold', 'platinum', 'emerald', 'diamond', 'master', 'grandmaster', 'challenger']
  const [tier, suffix] = rank.tier.toLowerCase().trim().split(/\s+/)
  const index = tiers.indexOf(tier)
  if (index < 0) return undefined
  const division = (rank.division || suffix || '').toUpperCase()
  if (valorant) {
    if (index >= 7) return 2100 + rank.rating
    const step = Number(division)
    return [1, 2, 3].includes(step) ? index * 300 + (step - 1) * 100 + rank.rating : undefined
  }
  if (index >= 7) return 2800 + rank.rating
  const step = ['IV', 'III', 'II', 'I'].indexOf(division)
  return step >= 0 ? index * 400 + step * 100 + rank.rating : undefined
}
