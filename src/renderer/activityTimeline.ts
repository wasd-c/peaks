import {dayDate, matchInterval} from './activityAnalytics'
import {valorantMapName} from './assets'
import {gameMode} from './riotProfile'
import type {Match} from './types'

export const TIMELINE_HOUR = 3_600_000
export const TIMELINE_HOURS = 24
export const TIMELINE_STEP_HOURS = 6

export interface TimelineMarker {kind: 'midnight' | 'now'; timestamp: number; left: number}

/** Calendar midnights are local dates, not successive 24-hour offsets (DST). */
export function timelineMarkers(start: number, now: number): TimelineMarker[] {
  if (!Number.isFinite(start)) return []
  const end = start + TIMELINE_HOURS * TIMELINE_HOUR
  const markers: TimelineMarker[] = []
  const midnight = new Date(start)
  midnight.setHours(0, 0, 0, 0)
  if (midnight.getTime() < start) { midnight.setDate(midnight.getDate() + 1); midnight.setHours(0, 0, 0, 0) }
  while (midnight.getTime() <= end) {
    const timestamp = midnight.getTime()
    markers.push({kind: 'midnight', timestamp, left: (timestamp - start) / (end - start) * 100})
    midnight.setDate(midnight.getDate() + 1)
    midnight.setHours(0, 0, 0, 0)
  }
  if (Number.isFinite(now) && now >= start && now < end) markers.push({kind: 'now', timestamp: now, left: (now - start) / (end - start) * 100})
  return markers.sort((a, b) => a.timestamp - b.timestamp)
}

/** Elapsed hours keep the scale exact across midnight and daylight-saving changes. */
export function timelineStart(date: string, offsetHours = 0) {
  return dayDate(date).getTime() + offsetHours * TIMELINE_HOUR
}

export function timelineMatches(matches: Match[], start: number) {
  const end = start + TIMELINE_HOURS * TIMELINE_HOUR
  return matches.flatMap(match => {
    const interval = matchInterval(match)
    const from = interval?.start ?? match.playedAtTimestamp
    if (typeof from !== 'number' || !Number.isFinite(from)) return []
    if (interval ? interval.end <= start || from >= end : from < start || from >= end) return []
    const clippedStart = Math.max(start, from)
    const clippedEnd = interval ? Math.min(end, interval.end) : clippedStart
    return [{match, start: from, end: interval?.end,
      left: (clippedStart - start) / (end - start) * 100,
      width: (clippedEnd - clippedStart) / (end - start) * 100}]
  })
}

/** Move exactly six elapsed hours, sliding the 24-hour canvas only at its edges. */
export function shiftTimeline(offsetHours: number, scrollHours: number, visibleHours: number, direction: -1 | 1) {
  const maxScroll = Math.max(0, TIMELINE_HOURS - visibleHours)
  const target = scrollHours + direction * TIMELINE_STEP_HOURS
  const slide = target < 0 ? -TIMELINE_STEP_HOURS : target > maxScroll ? TIMELINE_STEP_HOURS : 0
  return {offsetHours: offsetHours + slide, scrollHours: target - slide}
}

/** The lane already identifies the game. Avoid repeating it as map and queue. */
export function timelineMatchDetails(match: Match) {
  const normalize = (value: string) => value.trim().toLocaleLowerCase().replace(/[^\p{L}\p{N}]/gu, '')
  const redundant = new Set([match.game, ...(match.game === 'Teamfight Tactics' ? ['TFT'] : match.game === 'League of Legends' ? ['LoL', 'League'] : [])].map(normalize))
  const seen = new Set<string>()
  const details: string[] = []
  const mode = gameMode(match)
  const map = match.game === 'VALORANT' && match.map ? valorantMapName(match.map) : match.map
  for (const value of [match.game === 'Teamfight Tactics' && /^#?[1-8]$/.test(match.score ?? '') ? `#${match.score!.replace('#', '')}` : undefined, map, /^\d+$/.test(mode) ? undefined : mode]) {
    if (!value?.trim()) continue
    const normalized = normalize(value)
    if (!normalized || redundant.has(normalized) || seen.has(normalized) || ['unknown', 'inconnu', 'unknownqueue', 'match'].includes(normalized)) continue
    seen.add(normalized)
    details.push(value.trim())
  }
  return details
}
