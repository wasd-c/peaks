import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest'
import {shiftTimeline, TIMELINE_HOUR, timelineMarkers, timelineMatchDetails, timelineMatches, timelineStart} from './activityTimeline'
import type {Match} from './types'

const match = (id: string, timestamp: number, durationSeconds?: number): Match => ({id, game: 'Teamfight Tactics', result: 'Win', playedAtTimestamp: timestamp, durationSeconds})

describe('activity timeline navigation', () => {
  it('keeps exact durations and includes a game crossing either end of the 24-hour window', () => {
    const start = timelineStart('2026-09-20')
    const entries = timelineMatches([
      match('before', start - TIMELINE_HOUR, 1800),
      match('midnight', start - TIMELINE_HOUR / 2, 3600),
      match('evening', start + TIMELINE_HOUR * 23.5, 3600),
      match('after', start + TIMELINE_HOUR * 24, 3600),
    ], start)
    expect(entries.map(entry => entry.match.id)).toEqual(['midnight', 'evening'])
    expect(entries[0].left).toBe(0)
    expect(entries[0].width).toBeCloseTo(0.5 / 24 * 100)
    expect(entries[0].start).toBe(start - TIMELINE_HOUR / 2)
    expect(entries[0].end).toBe(start + TIMELINE_HOUR / 2)
    expect(entries[1].left + entries[1].width).toBeCloseTo(100)
  })

  it('keeps unknown durations as point markers without manufacturing playtime', () => {
    const start = timelineStart('2026-09-20')
    const entries = timelineMatches([match('unknown', start + TIMELINE_HOUR), match('future', start + TIMELINE_HOUR * 24)], start)
    expect(entries).toHaveLength(1)
    expect(entries[0].end).toBeUndefined()
    expect(entries[0].width).toBe(0)
  })

  it('moves by six hours inside the canvas and continues into adjacent days at its edges', () => {
    expect(shiftTimeline(0, 6, 6, 1)).toEqual({offsetHours: 0, scrollHours: 12})
    expect(shiftTimeline(0, 18, 6, 1)).toEqual({offsetHours: 6, scrollHours: 18})
    expect(shiftTimeline(0, 0, 6, -1)).toEqual({offsetHours: -6, scrollHours: 0})
    const first = shiftTimeline(0, 17, 6, 1)
    expect(first.offsetHours + first.scrollHours).toBe(23)
    const back = shiftTimeline(first.offsetHours, first.scrollHours, 6, -1)
    expect(back.offsetHours + back.scrollHours).toBe(17)
  })

  it('uses elapsed hours through local midnight without warping the 24-hour scale', () => {
    const date = '2026-10-25'
    expect(timelineStart(date, 24) - timelineStart(date)).toBe(24 * TIMELINE_HOUR)
    expect(timelineStart(date, -6)).toBe(timelineStart(date) - 6 * TIMELINE_HOUR)
  })

  it('omits repeated game names and map/queue duplicates while retaining placement and useful labels', () => {
    const base = match('tft', 1, 1800)
    expect(timelineMatchDetails({...base, map: 'Teamfight Tactics', mode: 'Teamfight Tactics'})).toEqual([])
    expect(timelineMatchDetails({...base, map: 'TFT', mode: 'Ranked', score: '#3'})).toEqual(['#3', 'Ranked'])
    expect(timelineMatchDetails({...base, game: 'VALORANT', map: 'Ascent', mode: 'Competitive'})).toEqual(['Ascent', 'Competitive'])
    expect(timelineMatchDetails({...base, map: 'Ranked', mode: 'Ranked'})).toEqual(['Ranked'])
    expect(timelineMatchDetails({...base, map: 'Teamfight Tactics', mode: '1100'})).toEqual(['Ranked'])
    expect(timelineMatchDetails({...base, map: 'Teamfight Tactics', mode: '1160'})).toEqual(['Double Up'])
    expect(timelineMatchDetails({...base, game: 'League of Legends', map: "Summoner's Rift", mode: '420'})).toEqual(["Summoner's Rift", 'Ranked solo / duo'])
    expect(timelineMatchDetails({...base, map: 'Teamfight Tactics', mode: '9999'})).toEqual([])
    expect(timelineMatchDetails({...base, map: 'Match'})).toEqual([])
  })

  it.each([
    ['Canyon', 'Fracture'], ['Duality', 'Bind'], ['Triad', 'Haven'],
    ['Infinity', 'Abyss'], ['Plummet', 'Summit'],
    ['/Game/Maps/Canyon/Canyon', 'Fracture'],
    ['224b0a95-48b9-f703-1bd8-67aca101a61f', 'Abyss'],
  ])('shows the map name instead of the Riot identifier %s', (map, name) => {
    expect(timelineMatchDetails({game: 'VALORANT', result: 'Win', map, mode: 'Swiftplay'})).toEqual([name, 'Swiftplay'])
  })
})

describe('local timeline guides', () => {
  beforeEach(() => vi.stubEnv('TZ', 'Europe/Paris'))
  afterEach(() => vi.unstubAllEnvs())

  it('places now on the exact elapsed scale without clamping it into an unrelated day', () => {
    const start = timelineStart('2026-09-20')
    expect(timelineMarkers(start, start + 6.5 * TIMELINE_HOUR).find(marker => marker.kind === 'now')?.left).toBeCloseTo(6.5 / 24 * 100)
    expect(timelineMarkers(start, start - 1).some(marker => marker.kind === 'now')).toBe(false)
    expect(timelineMarkers(start, start + 24 * TIMELINE_HOUR).some(marker => marker.kind === 'now')).toBe(false)
    expect(timelineMarkers(start, start).find(marker => marker.kind === 'now')?.left).toBe(0)
  })

  it('labels both local midnight boundaries of an ordinary day and the correct new day in a shifted window', () => {
    const start = timelineStart('2026-09-20')
    expect(timelineMarkers(start, 0).map(marker => marker.left)).toEqual([0, 100])
    const shifted = timelineMarkers(start + 6 * TIMELINE_HOUR, 0)
    expect(shifted).toEqual([{kind: 'midnight', timestamp: new Date(2026, 8, 21).getTime(), left: 75}])
  })

  it('finds both local midnights across the short DST day instead of assuming 24 hours between them', () => {
    const start = new Date(2026, 2, 28, 23, 30).getTime()
    const markers = timelineMarkers(start, 0)
    expect(markers.map(marker => marker.timestamp)).toEqual([new Date(2026, 2, 29).getTime(), new Date(2026, 2, 30).getTime()])
    expect(markers[1].timestamp - markers[0].timestamp).toBe(23 * TIMELINE_HOUR)
    expect(markers[1].left).toBeCloseTo(23.5 / 24 * 100)
  })

  it('does not put a midnight at 23:00 on the long DST day', () => {
    const start = new Date(2026, 9, 25).getTime()
    expect(timelineMarkers(start, 0)).toEqual([{kind: 'midnight', timestamp: start, left: 0}])
    const shifted = timelineMarkers(start + 6 * TIMELINE_HOUR, 0)
    expect(shifted).toHaveLength(1)
    expect(shifted[0].timestamp).toBe(new Date(2026, 9, 26).getTime())
    expect(shifted[0].left).toBeCloseTo(19 / 24 * 100)
  })
})
