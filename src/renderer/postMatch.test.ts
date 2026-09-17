import {describe, expect, it} from 'vitest'
import {
  advancePostMatchTracker,
  clearReviewedMatches,
  createPostMatchTracker,
  persistReviewedMatch,
  postMatchKey,
  readReviewedMatches,
  type ReviewStorage,
} from './postMatch'
import type {Account, CurrentMatch, Match} from './types'

const finalMatch: Match = {
  id: 'match-1', game: 'VALORANT', result: 'Win', map: 'Ascent', score: '13 — 8',
}
const account: Account = {id: 'owned-1', riotId: 'Player#EUW', region: 'EUW', ranks: [], owned: true}
const live: CurrentMatch = {id: 'match-1', game: 'VALORANT', phase: 'live', accountId: account.id}
const snapshot = (currentMatch: CurrentMatch, matches: Match[] = [], extraAccounts: Account[] = []) => ({
  accounts: [{...account, matches}, ...extraAccounts], currentMatch,
})
const begin = () => advancePostMatchTracker(createPostMatchTracker(), snapshot(live), 0).tracker

describe('post-match review detection', () => {
  it('does not announce history loaded on startup or a manual refresh', () => {
    let tracker = advancePostMatchTracker(createPostMatchTracker(), snapshot({}, [finalMatch]), 0).tracker
    const refreshed = advancePostMatchTracker(tracker, snapshot({}, [finalMatch, {...finalMatch, id: 'old'}]), 15_000)
    expect(refreshed.reviews).toEqual([])
    tracker = advancePostMatchTracker(refreshed.tracker, snapshot(live, [finalMatch]), 30_000).tracker
    expect(advancePostMatchTracker(tracker, snapshot({}, [finalMatch]), 45_000).reviews).toEqual([])
  })

  it('waits for the exact recorded result after the observed live match ends', () => {
    const waiting = advancePostMatchTracker(begin(), snapshot({}), 15_000)
    expect(waiting.reviews).toEqual([])
    const wrong = advancePostMatchTracker(waiting.tracker, snapshot({}, [{...finalMatch, id: 'unrelated'}]), 30_000)
    expect(wrong.reviews).toEqual([])
    const completed = advancePostMatchTracker(wrong.tracker, snapshot({}, [finalMatch]), 45_000)
    expect(completed.reviews).toEqual([{key: postMatchKey('VALORANT', 'match-1'), account: {...account, matches: [finalMatch]}, match: finalMatch}])
    expect(advancePostMatchTracker(completed.tracker, snapshot({}, [finalMatch]), 60_000).reviews).toEqual([])
  })

  it('defers a final record until the game leaves the live match', () => {
    const recording = advancePostMatchTracker(begin(), snapshot(live, [finalMatch]), 15_000)
    expect(recording.reviews).toEqual([])
    expect(advancePostMatchTracker(recording.tracker, snapshot({}, [finalMatch]), 30_000).reviews).toHaveLength(1)
  })

  it('ignores stale telemetry and waits for a confirmed transition', () => {
    const tracker = begin()
    const stale = advancePostMatchTracker(tracker, snapshot({...live, isStale: true}, [finalMatch]), 15_000)
    expect(stale).toEqual({tracker, reviews: []})
    expect(advancePostMatchTracker(stale.tracker, snapshot({}, [finalMatch]), 30_000).reviews).toHaveLength(1)
  })

  it('never arms an agent-select session or a stale first snapshot', () => {
    const pregame = advancePostMatchTracker(createPostMatchTracker(), snapshot({...live, phase: 'pregame'}), 0)
    expect(advancePostMatchTracker(pregame.tracker, snapshot({}, [finalMatch]), 15_000).reviews).toEqual([])
    const stale = advancePostMatchTracker(createPostMatchTracker(), snapshot({...live, isStale: true}), 0)
    expect(advancePostMatchTracker(stale.tracker, snapshot({}, [finalMatch]), 15_000).reviews).toEqual([])
  })

  it('requires an explicit live phase and the active owned account handle', () => {
    for (const current of [
      {...live, phase: undefined},
      {...live, accountId: undefined},
      {...live, accountId: 'not-owned'},
    ]) {
      const observed = advancePostMatchTracker(createPostMatchTracker(), snapshot(current), 0)
      expect(advancePostMatchTracker(observed.tracker, snapshot({}, [finalMatch]), 15_000).reviews).toEqual([])
    }
  })

  it('requires a terminal result and the original game/account identity', () => {
    const tracker = begin()
    expect(advancePostMatchTracker(tracker, snapshot({}, [{...finalMatch, result: 'Recent match'}]), 15_000).reviews).toEqual([])
    expect(advancePostMatchTracker(tracker, snapshot({}, [{...finalMatch, game: 'League of Legends'}]), 15_000).reviews).toEqual([])
    const unrelated = {...account, id: 'owned-2', matches: [finalMatch]}
    expect(advancePostMatchTracker(tracker, snapshot({}, [], [unrelated]), 15_000).reviews).toEqual([])
  })

  it('reviews the previous match when another game starts without an idle poll', () => {
    const nextLive = {...live, id: 'match-2'}
    const next = advancePostMatchTracker(begin(), snapshot(nextLive, [finalMatch]), 15_000)
    expect(next.reviews).toHaveLength(1)
    expect(next.tracker.observed.map(match => match.id)).toEqual(['match-2'])
  })

  it('accepts a recorded free-for-all scoreboard without a win/loss label', () => {
    const recorded: Match = {
      ...finalMatch, result: 'Recent match', freeForAll: true,
      teams: [{name: 'Players', players: [{name: 'You', self: true, stats: {kills: 40}}]}],
    }
    expect(advancePostMatchTracker(begin(), snapshot({}, [recorded]), 15_000).reviews).toHaveLength(1)
  })

  it('does not revive dismissed matches after restarting', () => {
    const initial = createPostMatchTracker([postMatchKey('VALORANT', 'match-1')])
    const observed = advancePostMatchTracker(initial, snapshot(live), 0)
    expect(advancePostMatchTracker(observed.tracker, snapshot({}, [finalMatch]), 15_000).reviews).toEqual([])
  })

  it('expires pending matches and leaves earlier tracker snapshots unchanged', () => {
    const tracker = begin()
    const copy = structuredClone(tracker)
    expect(advancePostMatchTracker(tracker, snapshot({}, [finalMatch]), 31 * 60_000).reviews).toEqual([])
    expect(tracker).toEqual(copy)
  })
})

describe('review acknowledgements', () => {
  it('stores only bounded match keys and clears them on reset', () => {
    const entries = new Map<string, string>()
    const storage: ReviewStorage = {
      getItem: key => entries.get(key) ?? null,
      setItem: (key, value) => { entries.set(key, value) },
      removeItem: key => { entries.delete(key) },
    }
    for (let index = 0; index < 300; index++) persistReviewedMatch(storage, postMatchKey('VALORANT', `match-${index}`))
    expect(readReviewedMatches(storage)).toHaveLength(256)
    expect([...entries.values()].join()).not.toContain(account.riotId)
    clearReviewedMatches(storage)
    expect(readReviewedMatches(storage)).toEqual([])
  })

  it('tolerates corrupt/blocked storage and rejects unrecognized values', () => {
    const storage: ReviewStorage = {
      getItem: () => '{broken',
      setItem: () => { throw new Error('Storage disabled') },
      removeItem: () => { throw new Error('Storage disabled') },
    }
    expect(readReviewedMatches(storage)).toEqual([])
    expect(() => persistReviewedMatch(storage, postMatchKey('VALORANT', 'match-1'))).not.toThrow()
    expect(() => clearReviewedMatches(storage)).not.toThrow()
    expect(createPostMatchTracker(['credentials', '["invalid","match-1"]']).deliveredKeys).toEqual([])
  })
})
