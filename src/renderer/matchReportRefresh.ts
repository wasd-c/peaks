import type {Account, Match, Player} from './types'

export interface MatchSelection {
  match: Match
  region?: string
  accountId?: string
  source?: 'player-profile'
}

export function resolveMatchReport(
  selection: MatchSelection,
  accounts: Account[],
  followed: Player[],
  preferredAccountId?: string,
): {match: Match; account?: Account} {
  // Search results carry the searched player's perspective, even when an
  // owned account participated in the same match.
  if (selection.source === 'player-profile') return {match: selection.match}
  const matchesSelection = (match: Match) => Boolean(selection.match.id)
    && match.id === selection.match.id && match.game === selection.match.game
  const owners = accounts.filter(account => account.owned !== false && account.matches?.some(matchesSelection))
  const account = owners.find(owner => owner.id === (selection.accountId ?? preferredAccountId)) ?? owners[0]
  const match = account?.matches?.find(matchesSelection)
    ?? [...accounts, ...followed].flatMap(owner => owner.matches ?? []).find(matchesSelection)
    ?? selection.match
  return {match, account: match.game === 'VALORANT' ? account : undefined}
}

export function matchReportNeedsRefresh(match: Match): boolean {
  return match.enrichmentPending === true
    || Boolean(match.teams?.some(team => team.players.some(player => !player.hidden && player.statsLoading)))
}

/** End transient loading in this view without changing the cached match. */
export function clearMatchReportLoading(match: Match): Match {
  if (!match.enrichmentPending && !match.teams?.some(team => team.players.some(player => player.statsLoading))) return match
  return {
    ...match,
    enrichmentPending: false,
    teams: match.teams?.map(team => ({
      ...team,
      players: team.players.map(player => player.statsLoading ? {...player, statsLoading: false} : player),
    })),
  }
}

/** One initial refresh also repairs stale cached identities. Only unfinished work is retried. */
export function startMatchReportRefresh({refresh, isPending, onStopped}: {
  refresh: () => Promise<void>
  isPending: () => boolean
  onStopped: () => void
}): () => void {
  let attempts = 0
  let inFlight = false
  let cancelled = false
  const cancel = () => {
    cancelled = true
    clearInterval(interval)
    clearTimeout(deadline)
  }
  const stop = () => {
    if (cancelled) return
    cancel()
    onStopped()
  }
  const request = async () => {
    if (cancelled || inFlight) return
    if (attempts > 0 && !isPending()) {
      cancel()
      return
    }
    attempts += 1
    inFlight = true
    try {
      await refresh()
      if (attempts >= 10) stop()
    } catch {
      stop()
    } finally {
      inFlight = false
    }
  }
  const interval = setInterval(() => void request(), 15_000)
  const deadline = setTimeout(stop, 3 * 60_000)
  void request()
  return cancel
}
