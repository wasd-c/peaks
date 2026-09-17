import type {Game, MatchPlayer, Player} from './types'

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
