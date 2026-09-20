import {findAccountIcon} from './accountIcons'
import {profileAgent, profileMatches, profilePlayer} from './accountProfile'
import type {Account, Game, Match, PlayerStats} from './types'

export type ProfileGame = 'riot' | Game
export const PROFILE_GAMES: Game[] = ['VALORANT', 'League of Legends', 'Teamfight Tactics']
const numeric = (value: unknown): value is number => typeof value === 'number' && Number.isFinite(value) && value >= 0
const sum = (values: number[]) => values.reduce((a, b) => a + b, 0)
const mean = (values: number[]) => values.length ? sum(values) / values.length : undefined
const rate = (count: number, total: number) => total ? 100 * count / total : undefined

export function championForMatch(match: Match, riotId: string) {
  const name = profilePlayer(match, riotId)?.agent ?? match.agent
  return name ? findAccountIcon({game: 'League of Legends', characterId: name}) : undefined
}

/** Most played in the available history; never presented as lifetime mastery. */
export function favoriteCharacter(account: Account, game: Game) {
  if (game === 'Teamfight Tactics') return undefined
  const counts = new Map<string, {id: string; name: string; count: number}>()
  for (const match of profileMatches(account.matches ?? [], game)) {
    const character = game === 'League of Legends' ? championForMatch(match, account.riotId)
      : findAccountIcon({game, characterId: profileAgent(match, account.riotId)})
    if (!character) continue
    const previous = counts.get(character.characterId)
    counts.set(character.characterId, {id: character.characterId, name: character.name, count: (previous?.count ?? 0) + 1})
  }
  // Input is newest first, so tied champions favor the most recently played.
  return [...counts.values()].sort((a, b) => b.count - a.count)[0]
}

export function gameMode(match: Match): string {
  if (match.teamMode === 'duos') return 'Double Up'
  const names: Record<string, string> = {
    '400': 'Normal draft', '420': 'Ranked solo / duo', '430': 'Normal blind',
    '440': 'Ranked flex', '450': 'ARAM', '490': 'Quickplay', '1700': 'Arena',
    '1090': 'Normal', '1100': 'Ranked', '1130': 'Hyper Roll', '1150': 'Double Up', '1160': 'Double Up',
    standard: 'Normal', ranked: 'Ranked', pairs: 'Double Up', turbo: 'Hyper Roll',
  }
  return names[(match.mode ?? '').toLowerCase()] ?? match.mode ?? 'Unknown queue'
}

export const validTftPlacement = (value: unknown): value is number => typeof value === 'number'
  && Number.isInteger(value) && value >= 1 && value <= 8

/** Keep raw places and classify Double Up only when its roster proves the scale. */
export function tftPositivePlacement(match: Match): 2 | 4 | undefined {
  if (gameMode(match) !== 'Double Up') return 4
  const placements = (match.teams ?? []).flatMap(team => team.players)
    .map(player => player.stats?.placement).filter(validTftPlacement)
  if (placements.some(placement => placement > 4)) return 4
  if (placements.length === 8 && [1, 2, 3, 4].every(place => placements.filter(value => value === place).length === 2)) return 2
  return undefined
}

export function leagueSummary(matches: Match[], riotId: string) {
  const rows = profileMatches(matches, 'League of Legends').map(match => ({match, player: profilePlayer(match, riotId)}))
  const stats = rows.flatMap(row => row.player?.stats ? [row.player.stats] : [])
  const kda = stats.filter(row => [row.kills, row.deaths, row.assists].every(numeric))
  const kills = sum(kda.map(row => row.kills!)), deaths = sum(kda.map(row => row.deaths!)), assists = sum(kda.map(row => row.assists!))
  const results = rows.map(row => row.match.result.toLowerCase())
  const wins = results.filter(result => ['win', 'victory'].includes(result)).length
  const losses = results.filter(result => ['defeat', 'loss'].includes(result)).length
  const perMinute = (key: keyof PlayerStats) => {
    const samples = rows.filter(({match, player}) => numeric(match.durationSeconds) && match.durationSeconds > 0 && numeric(player?.stats?.[key]))
    return samples.length ? sum(samples.map(row => row.player!.stats![key] as number)) / (sum(samples.map(row => row.match.durationSeconds!)) / 60) : undefined
  }
  const average = (key: keyof PlayerStats) => mean(stats.map(row => row[key]).filter(numeric))
  const participation = rows.flatMap(({match, player}) => {
    const team = match.teams?.find(row => player && row.players.includes(player))
    if (!player || !numeric(player.stats?.kills) || !numeric(player.stats?.assists) || !team || team.players.length !== 5 || !team.players.every(member => numeric(member.stats?.kills))) return []
    const teamKills = sum(team.players.map(member => member.stats!.kills!))
    return teamKills > 0 ? [{involved: player.stats.kills + player.stats.assists, teamKills}] : []
  })
  return {
    matches: rows.length, detailed: kda.length, wins, losses, winRate: rate(wins, wins + losses),
    kills: kda.length ? kills : undefined, deaths: kda.length ? deaths : undefined, assists: kda.length ? assists : undefined,
    kda: kda.length ? (kills + assists) / Math.max(deaths, 1) : undefined,
    csPerMinute: perMinute('minions'), damagePerMinute: perMinute('damage'),
    vision: average('vision'), gold: average('gold'), damage: average('damage'),
    killParticipation: participation.length ? rate(sum(participation.map(row => row.involved)), sum(participation.map(row => row.teamKills))) : undefined,
  }
}

export function championBreakdown(matches: Match[], riotId: string) {
  const groups = new Map<string, Match[]>()
  for (const match of profileMatches(matches, 'League of Legends')) {
    const champion = championForMatch(match, riotId)
    if (champion) groups.set(champion.characterId, [...groups.get(champion.characterId) ?? [], match])
  }
  return [...groups].map(([id, rows]) => ({id, champion: findAccountIcon({game: 'League of Legends', characterId: id})!, ...leagueSummary(rows, riotId)}))
    .sort((a, b) => b.matches - a.matches)
}

export function tftSummary(matches: Match[], riotId: string, duos = false) {
  const rows = profileMatches(matches, 'Teamfight Tactics').filter(match => (match.teamMode === 'duos' || gameMode(match) === 'Double Up') === duos)
  const results = rows.map(match => ({placement: profilePlayer(match, riotId)?.stats?.placement, cutoff: tftPositivePlacement(match)}))
  const placements = results.map(row => row.placement).filter(validTftPlacement)
  const classified = results.flatMap(({placement, cutoff}) => validTftPlacement(placement) && cutoff != null ? [{placement, cutoff}] : [])
  const cutoffs = [...new Set(classified.map(row => row.cutoff))]
  const positivePlacement = cutoffs.length === 1 ? cutoffs[0] : undefined
  const wins = placements.filter(value => value === 1).length
  return {
    matches: rows.length, detailed: placements.length, average: mean(placements), wins: placements.length ? wins : undefined,
    winRate: rate(wins, placements.length), topRate: rate(classified.filter(row => row.placement <= row.cutoff).length, classified.length), positivePlacement,
    distribution: Array.from({length: duos && results.every(row => row.cutoff === 2) ? 4 : 8}, (_, index) => ({placement: index + 1, count: placements.filter(value => value === index + 1).length})),
    compositions: rows.filter(match => profilePlayer(match, riotId)?.composition?.units != null).length,
  }
}
