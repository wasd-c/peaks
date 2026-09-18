import type {Account, Game, Match, MatchPlayer, Player, Rank} from './types'

export const samePlayerIdentity = (left: Player, right: Player) => {
  const leftRiotId = left.riotId.trim()
  const rightRiotId = right.riotId.trim()
  if (leftRiotId && rightRiotId) {
    return leftRiotId.localeCompare(rightRiotId, undefined, {sensitivity: 'base'}) === 0
  }
  return Boolean(left.id) && left.id === right.id
}

export const playerIsWatched = (player: Player, followed: Player[]) => (
  followed.some(candidate => samePlayerIdentity(candidate, player))
)

/** Compatibility alias for existing state consumers. */
export const playerIsFollowed = playerIsWatched

const availableRank = (rank?: string) => Boolean(rank?.trim() && !/unavailable|unknown/i.test(rank))

/** Merge only evidence for this Riot identity; a match's game remains context,
 * never a filter on the identity's other games. Never borrow a teammate's data. */
export function mergeRiotProfile(selected: Player, accounts: Account[], followed: Player[], fetched: Player[] = []): Player {
  const identityMatches = (candidate: Player) => samePlayerIdentity(selected, candidate)
  const accountProfiles: Player[] = accounts.filter(account => identityMatches(account)).map(account => ({
    id: account.id, riotId: account.riotId, region: account.region, ranks: account.ranks,
    peakRanks: account.peakRanks, matches: account.matches, lastUpdated: account.lastUpdated,
  }))
  const sources = [...followed.filter(identityMatches), ...accountProfiles, selected, ...fetched.filter(identityMatches)]
  const ranks = new Map<Game, Rank>()
  const peaks = new Map<Game, Rank>()
  const games = new Set<Game>()
  for (const source of sources) {
    for (const game of source.games ?? []) games.add(game)
    if (source.game) games.add(source.game)
    for (const match of source.matches ?? []) games.add(match.game)
    for (const rank of source.ranks ?? []) if (availableRank(rank.tier)) { ranks.set(rank.game, rank); games.add(rank.game) }
    for (const peak of source.peakRanks ?? []) if (availableRank(peak.tier)) { peaks.set(peak.game, peak); games.add(peak.game) }
    if (source.game && availableRank(source.currentRank) && !ranks.has(source.game)) ranks.set(source.game, {game: source.game, tier: source.currentRank!})
    if (source.game && availableRank(source.peakRank) && !peaks.has(source.game)) peaks.set(source.game, {game: source.game, tier: source.peakRank!})
  }
  const matches = new Map<string, Match>()
  for (const source of [...sources].reverse()) for (const match of source.matches ?? []) {
    const key = JSON.stringify([match.game, match.id ?? [match.playedAt, match.map, match.mode, match.score, match.agent]])
    if (!matches.has(key)) matches.set(key, match)
  }
  const recent = [...sources].reverse()
  return {
    ...selected,
    region: recent.find(source => source.region && source.region !== 'GLOBAL')?.region ?? selected.region,
    lastUpdated: recent.find(source => source.lastUpdated)?.lastUpdated,
    lastGame: recent.find(source => source.lastGame)?.lastGame,
    games: [...games], ranks: [...ranks.values()], peakRanks: [...peaks.values()], matches: [...matches.values()],
  }
}

interface MatchPlayerProfileContext {
  game: Game
  region?: string
  team?: string
  label: string
  matchId?: string
  map?: string
  result?: string
}

export function matchPlayerProfile(
  player: MatchPlayer,
  context: MatchPlayerProfileContext,
): Player | null {
  if (player.hidden) return null
  const riotId = player.riotId ?? (player.name.includes('#') ? player.name : undefined)
  if (!riotId) return null
  const initials = riotId
    .replace('#', ' ')
    .split(/\s+/)
    .map(part => part.charAt(0))
    .join('')
    .slice(0, 2)
    .toUpperCase()
  return {
    id: `riot:${context.game.toLowerCase().replace(/[^a-z0-9]+/g, '-')}:${riotId.toLowerCase()}`,
    riotId,
    region: player.region ?? context.region ?? 'GLOBAL',
    game: context.game,
    games: [context.game],
    currentRank: player.currentRank ?? player.rank ?? 'Rank unavailable',
    peakRank: player.peakRank,
    level: player.accountLevel,
    lastGame: context.label,
    lastUpdated: context.label,
    initials,
    context: {
      label: context.label,
      matchId: context.matchId,
      map: context.map,
      result: context.result,
      team: context.team,
      character: player.agent,
      score: player.score,
      stats: player.stats,
    },
  }
}
