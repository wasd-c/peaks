import type {Match, MatchPlayer} from './types'

export interface PerformanceBreakdown {
  label: string
  games: number
  wins: number
  losses: number
  winRate?: number
  kills: number
  deaths: number
  assists: number
  kd?: number
  averageCombatScore?: number
}

export interface TeammateInsight {
  riotId: string
  games: number
  wins: number
  winRate?: number
}

export interface MatchTrend {
  id: string
  map: string
  mode: string
  result: string
  score?: string
  kda?: string
  averageCombatScore?: number
  rrDelta?: number
  playedAt?: string
}

export interface ValorantInsights {
  matches: number
  wins: number
  losses: number
  winRate?: number
  kd?: number
  averageCombatScore?: number
  averageDamagePerRound?: number
  headshotRate?: number
  rrDelta?: number
  agents: PerformanceBreakdown[]
  maps: PerformanceBreakdown[]
  teammates: TeammateInsight[]
  trend: MatchTrend[]
}

interface MutablePerformance {
  label: string
  games: number
  wins: number
  losses: number
  kills: number
  deaths: number
  assists: number
  combatScoreTotal: number
  combatScoreSamples: number
}

const normalizeIdentity = (value: string) => value.trim().toLocaleLowerCase()

const resultKind = (result: string) => {
  const normalized = result.trim().toLocaleLowerCase()
  if (normalized === 'win' || normalized === 'victory') return 'win'
  if (normalized === 'loss' || normalized === 'defeat') return 'loss'
  return 'other'
}

const playerIdentity = (player: MatchPlayer) => normalizeIdentity(player.riotId ?? player.name)

function ownPlayer(match: Match, riotId: string) {
  const players = (match.teams ?? []).flatMap(team => team.players)
  return players.find(player => !player.hidden && playerIdentity(player) === normalizeIdentity(riotId))
}

function averageCombatScore(player?: MatchPlayer) {
  const score = player?.stats?.combatScore
  if (score == null) return undefined
  const rounds = player?.stats?.roundsPlayed
  return rounds != null && rounds > 0 ? score / rounds : undefined
}

function damagePerRound(player?: MatchPlayer) {
  const damage = player?.stats?.damage
  if (damage == null) return undefined
  const rounds = player?.stats?.roundsPlayed
  return rounds != null && rounds > 0 ? damage / rounds : undefined
}

function rrDelta(match: Match) {
  const value = match.delta?.match(/[+-]?\d+/)?.[0]
  if (!value) return undefined
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : undefined
}

function addPerformance(
  groups: Map<string, MutablePerformance>,
  label: string,
  result: ReturnType<typeof resultKind>,
  player?: MatchPlayer,
) {
  const key = label.trim().toLocaleLowerCase()
  const current = groups.get(key) ?? {
    label,
    games: 0,
    wins: 0,
    losses: 0,
    kills: 0,
    deaths: 0,
    assists: 0,
    combatScoreTotal: 0,
    combatScoreSamples: 0,
  }
  current.games += 1
  current.wins += result === 'win' ? 1 : 0
  current.losses += result === 'loss' ? 1 : 0
  current.kills += player?.stats?.kills ?? 0
  current.deaths += player?.stats?.deaths ?? 0
  current.assists += player?.stats?.assists ?? 0
  const score = averageCombatScore(player)
  if (score != null) {
    current.combatScoreTotal += score
    current.combatScoreSamples += 1
  }
  groups.set(key, current)
}

function finalizeBreakdowns(groups: Map<string, MutablePerformance>) {
  return [...groups.values()]
    .map<PerformanceBreakdown>(group => ({
      label: group.label,
      games: group.games,
      wins: group.wins,
      losses: group.losses,
      winRate: group.wins + group.losses > 0
        ? (group.wins / (group.wins + group.losses)) * 100
        : undefined,
      kills: group.kills,
      deaths: group.deaths,
      assists: group.assists,
      kd: group.deaths > 0 ? group.kills / group.deaths : group.kills > 0 ? group.kills : undefined,
      averageCombatScore: group.combatScoreSamples > 0
        ? group.combatScoreTotal / group.combatScoreSamples
        : undefined,
    }))
    .sort((left, right) => right.games - left.games || right.wins - left.wins || left.label.localeCompare(right.label))
}

export function valorantInsights(matches: Match[], riotId: string): ValorantInsights {
  const valorantMatches = matches.filter(match => match.game === 'VALORANT')
  const agentGroups = new Map<string, MutablePerformance>()
  const mapGroups = new Map<string, MutablePerformance>()
  const teammateGroups = new Map<string, TeammateInsight>()
  let wins = 0
  let losses = 0
  let kills = 0
  let deaths = 0
  let combatScoreTotal = 0
  let combatScoreSamples = 0
  let damageTotal = 0
  let damageSamples = 0
  let headshots = 0
  let shots = 0
  let rankRatingDelta = 0
  let rankRatingSamples = 0

  const trend = valorantMatches.map<MatchTrend>((match, index) => {
    const result = resultKind(match.result)
    const player = ownPlayer(match, riotId)
    const stats = player?.stats
    wins += result === 'win' ? 1 : 0
    losses += result === 'loss' ? 1 : 0
    kills += stats?.kills ?? 0
    deaths += stats?.deaths ?? 0

    const combatScore = averageCombatScore(player)
    if (combatScore != null) {
      combatScoreTotal += combatScore
      combatScoreSamples += 1
    }
    const roundDamage = damagePerRound(player)
    if (roundDamage != null) {
      damageTotal += roundDamage
      damageSamples += 1
    }
    if (stats?.headshots != null && stats.bodyshots != null && stats.legshots != null) {
      headshots += stats.headshots
      shots += stats.headshots + stats.bodyshots + stats.legshots
    }
    const matchDelta = rrDelta(match)
    if (matchDelta != null) {
      rankRatingDelta += matchDelta
      rankRatingSamples += 1
    }

    addPerformance(agentGroups, player?.agent ?? 'Agent unavailable', result, player)
    addPerformance(mapGroups, match.map ?? 'Map unavailable', result, player)

    if (!match.freeForAll) {
      const ownTeam = (match.teams ?? []).find(team => team.players.some(candidate => (
        candidate.self || playerIdentity(candidate) === normalizeIdentity(riotId)
      )))
      for (const teammate of ownTeam?.players ?? []) {
        const teammateRiotId = teammate.riotId ?? teammate.name
        const normalized = playerIdentity(teammate)
        if (teammate.self || teammate.hidden || normalized === normalizeIdentity(riotId)) continue
        const current = teammateGroups.get(normalized) ?? {riotId: teammateRiotId, games: 0, wins: 0}
        current.games += 1
        current.wins += result === 'win' ? 1 : 0
        teammateGroups.set(normalized, current)
      }
    }

    return {
      id: match.id ?? `valorant-match-${index}`,
      map: match.map ?? 'Map unavailable',
      mode: match.mode ?? 'Match',
      result: match.result,
      score: match.score,
      kda: stats && [stats.kills, stats.deaths, stats.assists].some(value => value != null)
        ? `${stats.kills ?? 0} / ${stats.deaths ?? 0} / ${stats.assists ?? 0}`
        : undefined,
      averageCombatScore: combatScore,
      rrDelta: matchDelta,
      playedAt: match.playedAt,
    }
  })

  const ratedMatches = wins + losses
  return {
    matches: valorantMatches.length,
    wins,
    losses,
    winRate: ratedMatches > 0 ? (wins / ratedMatches) * 100 : undefined,
    kd: deaths > 0 ? kills / deaths : kills > 0 ? kills : undefined,
    averageCombatScore: combatScoreSamples > 0 ? combatScoreTotal / combatScoreSamples : undefined,
    averageDamagePerRound: damageSamples > 0 ? damageTotal / damageSamples : undefined,
    headshotRate: shots > 0 ? (headshots / shots) * 100 : undefined,
    rrDelta: rankRatingSamples > 0 ? rankRatingDelta : undefined,
    agents: finalizeBreakdowns(agentGroups),
    maps: finalizeBreakdowns(mapGroups),
    teammates: [...teammateGroups.values()]
      .map(teammate => ({
        ...teammate,
        winRate: teammate.games > 0 ? (teammate.wins / teammate.games) * 100 : undefined,
      }))
      .sort((left, right) => right.games - left.games || right.wins - left.wins || left.riotId.localeCompare(right.riotId))
      .slice(0, 8),
    trend: trend.slice(0, 10),
  }
}
