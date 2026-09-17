import {afterEach, describe, expect, it, vi} from 'vitest'
import {
  clearMatchReportLoading,
  matchReportNeedsRefresh,
  resolveMatchReport,
  startMatchReportRefresh,
} from './matchReportRefresh'
import type {Account, Match} from './types'

const match: Match = {
  id: 'match-1', game: 'VALORANT', result: 'Win',
  teams: [{name: 'Allies', players: [{name: 'You', self: true, statsLoading: true}]}],
}
const owner = (id: string, report: Match = match): Account => ({
  id, riotId: `${id}#EUW`, region: 'EUW', ranks: [], matches: [report], owned: true,
})

afterEach(() => vi.useRealTimers())

describe('match report selection and loading', () => {
  it('uses the originating account when the same match appears in multiple histories', () => {
    const otherReport = {...match, score: '13 : 7'}
    const ownReport = {...match, score: '7 : 13'}
    const accounts = [owner('first', otherReport), owner('selected', ownReport)]
    const resolved = resolveMatchReport({match, accountId: 'selected'}, accounts, [], 'first')
    expect(resolved.account?.id).toBe('selected')
    expect(resolved.match).toBe(ownReport)
    expect(resolveMatchReport({match}, accounts, [], 'selected').account?.id).toBe('selected')
  })

  it('keeps the searched player perspective when an owned account played the same match', () => {
    const searchedReport: Match = {
      ...match,
      teams: [{name: 'Allies', players: [{name: 'Searched#TAG', self: true, stats: {kills: 24, deaths: 15, assists: 4}}]}],
    }
    const ownedReport: Match = {
      ...match,
      teams: [{name: 'Allies', players: [{name: 'Owned#TAG', self: true, stats: {kills: 8, deaths: 20, assists: 2}}]}],
    }
    const accounts = [owner('owned-account', ownedReport)]
    const resolved = resolveMatchReport({match: searchedReport, source: 'player-profile'}, accounts, [], 'owned-account')
    expect(resolved.match).toBe(searchedReport)
    expect(resolved.account).toBeUndefined()
    expect(resolved.match.teams?.[0].players[0]).toMatchObject({name: 'Searched#TAG', self: true, stats: {kills: 24}})
  })

  it('never refreshes through a followed account or treats unrelated matches as identical', () => {
    const followedOwner = {...owner('followed'), owned: false}
    expect(resolveMatchReport({match, accountId: 'followed'}, [followedOwner], []).account).toBeUndefined()
    const league: Match = {...match, game: 'League of Legends'}
    expect(resolveMatchReport({match: league}, [owner('first')], []).match).toBe(league)
    const withoutId: Match = {...match, id: undefined}
    expect(resolveMatchReport({match: withoutId}, [owner('first')], []).match).toBe(withoutId)
  })

  it('keeps fetching visible player statistics even when roster enrichment is finished', () => {
    expect(matchReportNeedsRefresh(match)).toBe(true)
    expect(matchReportNeedsRefresh({...match, teams: [{name: 'Hidden', players: [{name: 'Hidden player', hidden: true, statsLoading: true}]}]})).toBe(false)
    expect(matchReportNeedsRefresh({...match, teams: [], enrichmentPending: true})).toBe(true)
  })

  it('stops only transient view flags, preserving identities, stats and the cached object', () => {
    const original: Match = {...match, enrichmentPending: true, teams: [{name: 'Allies', players: [{name: 'You', stats: {kills: 24}, statsLoading: true}]}]}
    const finished = clearMatchReportLoading(original)
    expect(finished.enrichmentPending).toBe(false)
    expect(finished.teams?.[0].players[0]).toEqual({name: 'You', stats: {kills: 24}, statsLoading: false})
    expect(original.enrichmentPending).toBe(true)
    expect(original.teams?.[0].players[0].statsLoading).toBe(true)
  })
})

describe('bounded match report refresh', () => {
  it('refreshes a cached report once even when no pending flags were persisted', async () => {
    vi.useFakeTimers()
    const refresh = vi.fn().mockResolvedValue(undefined)
    const onStopped = vi.fn()
    startMatchReportRefresh({refresh, isPending: () => false, onStopped})
    expect(refresh).toHaveBeenCalledTimes(1)
    await vi.advanceTimersByTimeAsync(180_000)
    expect(refresh).toHaveBeenCalledTimes(1)
    expect(onStopped).not.toHaveBeenCalled()
  })

  it('retries outstanding statistics and clears loading at the attempt limit', async () => {
    vi.useFakeTimers()
    const refresh = vi.fn().mockResolvedValue(undefined)
    const onStopped = vi.fn()
    startMatchReportRefresh({refresh, isPending: () => true, onStopped})
    await vi.advanceTimersByTimeAsync(180_000)
    expect(refresh).toHaveBeenCalledTimes(10)
    expect(onStopped).toHaveBeenCalledTimes(1)
  })

  it('stops after a failed fetch instead of leaving spinners active', async () => {
    vi.useFakeTimers()
    const refresh = vi.fn().mockRejectedValue(new Error('Session unavailable'))
    const onStopped = vi.fn()
    startMatchReportRefresh({refresh, isPending: () => true, onStopped})
    await vi.advanceTimersByTimeAsync(180_000)
    expect(refresh).toHaveBeenCalledTimes(1)
    expect(onStopped).toHaveBeenCalledTimes(1)
  })

  it('does not overlap requests and ends a hung request at the time limit', async () => {
    vi.useFakeTimers()
    const refresh = vi.fn(() => new Promise<void>(() => {}))
    const onStopped = vi.fn()
    startMatchReportRefresh({refresh, isPending: () => true, onStopped})
    await vi.advanceTimersByTimeAsync(180_000)
    expect(refresh).toHaveBeenCalledTimes(1)
    expect(onStopped).toHaveBeenCalledTimes(1)
  })

  it('does not update a closed report when an outstanding request rejects', async () => {
    vi.useFakeTimers()
    let reject: (error: Error) => void = () => {}
    const refresh = vi.fn(() => new Promise<void>((_, fail) => { reject = fail }))
    const onStopped = vi.fn()
    const cancel = startMatchReportRefresh({refresh, isPending: () => true, onStopped})
    cancel()
    reject(new Error('Late failure'))
    await vi.advanceTimersByTimeAsync(180_000)
    expect(refresh).toHaveBeenCalledTimes(1)
    expect(onStopped).not.toHaveBeenCalled()
  })
})
