import type {Account, AppState, Game, Match} from './types'

export const POST_MATCH_REVIEW_KEY = 'peaks.post-match.reviewed.v1'
const MAX_REVIEW_KEYS = 256
const RECORDING_WAIT_MS = 30 * 60 * 1000
const GAMES = new Set<Game>(['League of Legends', 'VALORANT', 'Teamfight Tactics'])
const FINISHED_RESULTS = new Set(['win', 'victory', 'loss', 'defeat', 'draw', 'tie', 'top 4', 'placement'])

const hasFinalRecord = (match: Match) => FINISHED_RESULTS.has(match.result.trim().toLowerCase())
  || Boolean(match.freeForAll && match.teams?.some(team => team.players.length > 0))

type MatchSnapshot = Pick<AppState, 'accounts' | 'currentMatch'>

interface ObservedMatch {
  key: string
  game: Game
  id: string
  accountId: string
  lastObservedAt: number
}

export interface PostMatchReview {
  key: string
  account: Account
  match: Match
}

export interface PostMatchTracker {
  initialized: boolean
  baselineKeys: readonly string[]
  deliveredKeys: readonly string[]
  observed: readonly ObservedMatch[]
}

export interface ReviewStorage {
  getItem(key: string): string | null
  setItem(key: string, value: string): void
  removeItem(key: string): void
}

const validMatchId = (id: unknown): id is string => typeof id === 'string'
  && id.length > 0 && id.length <= 256
  && [...id].every(character => character.charCodeAt(0) >= 32 && character.charCodeAt(0) !== 127)

export function postMatchKey(game: Game, id: string): string {
  return JSON.stringify([game, id])
}

function validReviewKey(key: unknown): key is string {
  if (typeof key !== 'string' || key.length > 320) return false
  try {
    const value: unknown = JSON.parse(key)
    return Array.isArray(value) && value.length === 2
      && GAMES.has(value[0] as Game) && validMatchId(value[1])
  } catch {
    return false
  }
}

export function createPostMatchTracker(reviewedKeys: readonly string[] = []): PostMatchTracker {
  return {
    initialized: false,
    baselineKeys: [],
    deliveredKeys: reviewedKeys.filter(validReviewKey).slice(-MAX_REVIEW_KEYS),
    observed: [],
  }
}

/**
 * A recorded row only becomes a review after that exact game was observed live.
 * Missing activity alone cannot imply a result: the final owned-account record
 * must also arrive, even when the provider publishes it several polls later.
 */
export function advancePostMatchTracker(
  tracker: PostMatchTracker,
  snapshot: MatchSnapshot,
  now: number,
): {tracker: PostMatchTracker; reviews: PostMatchReview[]} {
  const current = snapshot.currentMatch
  if (current.isStale) return {tracker, reviews: []}
  const currentKey = current.game && validMatchId(current.id)
    ? postMatchKey(current.game, current.id) : null
  const baselineKeys = tracker.initialized ? tracker.baselineKeys : snapshot.accounts.flatMap(account => (
    (account.matches ?? []).filter(match => validMatchId(match.id)).map(match => postMatchKey(match.game, match.id!))
  ))
  const excluded = new Set([...baselineKeys, ...tracker.deliveredKeys])
  const observed = tracker.observed.filter(match => now - match.lastObservedAt <= RECORDING_WAIT_MS)
  const activeAccount = snapshot.accounts.find(account => account.id === current.accountId && account.owned !== false)
  const live = current.phase === 'live' && activeAccount

  if (currentKey && current.game && current.id && live && !excluded.has(currentKey)) {
    const existing = observed.findIndex(match => match.key === currentKey)
    const match = {
      key: currentKey, game: current.game, id: current.id,
      accountId: activeAccount.id, lastObservedAt: now,
    }
    if (existing >= 0) observed[existing] = match
    else observed.push(match)
  }

  const reviews: PostMatchReview[] = []
  const remaining: ObservedMatch[] = []
  for (const pending of observed) {
    if (excluded.has(pending.key)) continue
    // A final record can arrive before the client leaves the match. Keep it
    // pending until that live ID disappears or a different match takes over.
    if (pending.key === currentKey) {
      remaining.push(pending)
      continue
    }
    let review: PostMatchReview | undefined
    for (const account of snapshot.accounts) {
      if (account.owned === false) continue
      if (account.id !== pending.accountId) continue
      const match = account.matches?.find(candidate => candidate.id === pending.id
        && candidate.game === pending.game
        && hasFinalRecord(candidate))
      if (match) {
        review = {key: pending.key, account, match}
        break
      }
    }
    if (review) {
      reviews.push(review)
      excluded.add(pending.key)
    } else remaining.push(pending)
  }

  return {
    tracker: {
      initialized: true,
      baselineKeys,
      deliveredKeys: [...tracker.deliveredKeys, ...reviews.map(review => review.key)].slice(-MAX_REVIEW_KEYS),
      observed: remaining.slice(-16),
    },
    reviews,
  }
}

export function getReviewStorage(): ReviewStorage | null {
  try {
    return typeof window === 'undefined' ? null : window.localStorage
  } catch {
    return null
  }
}

export function readReviewedMatches(storage: ReviewStorage | null): string[] {
  try {
    const raw = storage?.getItem(POST_MATCH_REVIEW_KEY)
    if (!raw || raw.length > 100_000) return []
    const parsed: unknown = JSON.parse(raw)
    return Array.isArray(parsed) ? parsed.filter(validReviewKey).slice(-MAX_REVIEW_KEYS) : []
  } catch {
    return []
  }
}

export function persistReviewedMatch(storage: ReviewStorage | null, key: string): void {
  if (!validReviewKey(key)) return
  try {
    const reviewed = readReviewedMatches(storage).filter(value => value !== key)
    // Only game names and match IDs persist. Account data, stats and credentials
    // stay out of browser storage; current-session deduplication also works if
    // storage is blocked or full.
    storage?.setItem(POST_MATCH_REVIEW_KEY, JSON.stringify([...reviewed, key].slice(-MAX_REVIEW_KEYS)))
  } catch {
    // The tracker has already delivered this review once in memory.
  }
}

export function clearReviewedMatches(storage: ReviewStorage | null): void {
  try {
    storage?.removeItem(POST_MATCH_REVIEW_KEY)
  } catch {
    // A reset remains usable when browser storage is unavailable.
  }
}
