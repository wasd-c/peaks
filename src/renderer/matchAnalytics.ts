import type {Game, Match, MatchPlayer, PlayerStats} from './types'
import {hasValidRoundEvents, hasValidWeaponEvents, isStatCount, selectPerformanceTags, type PerformanceTag} from './performanceTags'

export type MatchAnalyticsStats = PlayerStats
export type {PerformanceTag} from './performanceTags'

const isCount = isStatCount
const normalized = (value: string) => value.trim().toLocaleLowerCase()

export function matchAnalytics(matches: Match[], riotId?: string) {
  const valorantMatches = matches.filter(match => match.game === 'VALORANT')
  const selected = valorantMatches.flatMap(match => {
    const players = match.teams?.flatMap(team => team.players) ?? []
    const player = riotId
      ? players.find(candidate => normalized(candidate.riotId ?? candidate.name) === normalized(riotId))
      : players.find(candidate => candidate.self)
    return player && !player.hidden && player.stats ? [player.stats as MatchAnalyticsStats] : []
  })

  return analyzePlayerStats(selected, valorantMatches.length)
}

export function playerPerformanceTags(player: MatchPlayer, game: Game): PerformanceTag[] {
  if (game !== 'VALORANT' || player.hidden || !player.stats) return []
  return analyzePlayerStats([player.stats as MatchAnalyticsStats]).tags
}

/** Recent-history tags are never derived from the current game's statistics. */
export function historicalPerformanceTags(player: MatchPlayer, game: Game): PerformanceTag[] {
  const stats = player.overallStats
  if (game !== 'VALORANT' || player.hidden || !stats || !isCount(stats.matchesPlayed)) return []
  return selectPerformanceTags([stats], {context: 'history', expectedMatches: 1, aggregatedMatches: stats.matchesPlayed})
}

function analyzePlayerStats(selected: MatchAnalyticsStats[], expectedMatches = selected.length) {
  let head = 0
  let body = 0
  let feet = 0
  let hitMatches = 0
  let weaponMatches = 0
  let roundMatches = 0
  const weaponCounts = new Map<string, {weapon: string; kills: number}>()

  for (const stats of selected) {
    // A missing location is not a zero: percentages require the complete hit split.
    if (isCount(stats.headshots) && isCount(stats.bodyshots) && isCount(stats.legshots)) {
      head += stats.headshots
      body += stats.bodyshots
      feet += stats.legshots
      hitMatches += 1
    }
    const validWeapons = hasValidWeaponEvents(stats)
    if (validWeapons && stats.weaponUsage) {
      weaponMatches += 1
      for (const entry of stats.weaponUsage) {
        const key = normalized(entry.weapon)
        const existing = weaponCounts.get(key)
        weaponCounts.set(key, {weapon: existing?.weapon ?? entry.weapon, kills: (existing?.kills ?? 0) + entry.kills})
      }
    }
    if (hasValidRoundEvents(stats)) roundMatches += 1
  }

  const totalHits = head + body + feet
  const weaponKills = [...weaponCounts.values()].reduce((total, item) => total + item.kills, 0)
  const tags = selectPerformanceTags(selected, {context: expectedMatches > 1 ? 'history' : 'match', expectedMatches})

  return {
    hitMatches,
    weaponMatches,
    roundMatches,
    totalHits,
    tags,
    hitDistribution: [
      {label: 'Head', hits: head},
      {label: 'Body', hits: body},
      {label: 'Feet', hits: feet},
    ].map(item => ({...item, percentage: totalHits > 0 ? item.hits / totalHits * 100 : undefined})),
    weapons: [...weaponCounts.values()]
      .filter(item => item.kills > 0)
      .sort((left, right) => right.kills - left.kills || left.weapon.localeCompare(right.weapon))
      .map(item => ({...item, percentage: weaponKills > 0 ? item.kills / weaponKills * 100 : undefined})),
  }
}
