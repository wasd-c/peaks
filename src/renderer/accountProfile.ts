import {valorantAgentName, valorantMapName} from './assets'
import roles from './valorantRoles.json'
import type {Account, AppState, Game, Match, MatchPlayer, PlayerStats} from './types'

export function profileAccount(state: AppState, id?: string | null): Account | undefined {
  return state.accounts.find(account => account.id === id && account.owned !== false)
}

export function approvedProfileAccount(command: string, state: AppState): Account | undefined {
  return ['add_account', 'import_session', 'connect_riot_client', 'connect_riot_qr_image'].includes(command)
    ? profileAccount(state, state.openedAccountId) : undefined
}

export function profilePlayer(match: Match, riotId: string): MatchPlayer | undefined {
  const players = (match.teams ?? []).flatMap(team => team.players)
  const exact = players.filter(player => !player.hidden && (player.riotId ?? player.name).trim().toLowerCase() === riotId.trim().toLowerCase())
  if (exact.length) return exact.length === 1 ? exact[0] : undefined
  const selves = players.filter(player => player.self)
  if (selves.length !== 1 || selves[0].hidden) return undefined
  // The backend binds self to the requested PUUID; a historical Riot ID may
  // differ after a rename. An exact visible identity still takes precedence.
  return selves[0]
}

export function profileMatches(matches: Match[], game: Game = 'VALORANT'): Match[] {
  const seen = new Set<string>()
  return matches.filter(match => {
    if (match.game !== game || (match.id && seen.has(match.id))) return false
    if (match.id) seen.add(match.id)
    return true
  }).sort((a, b) => (b.playedAtTimestamp ?? 0) - (a.playedAtTimestamp ?? 0))
}

export function profileMode(match: Match): string {
  return match.freeForAll ? 'deathmatch' : (match.mode ?? 'unknown').toLowerCase()
}

export const profileAgent = (match: Match, riotId: string) => valorantAgentName(profilePlayer(match, riotId)?.agent ?? match.agent) ?? 'Agent unavailable'
export const profileRole = (match: Match, riotId: string) => (roles as Record<string, string>)[profileAgent(match, riotId)] ?? 'Unknown role'

export interface ProfileFilters {mode: string; season: string; agent: string; map: string}
export function filterProfileMatches(matches: Match[], riotId: string, filters: ProfileFilters): Match[] {
  return profileMatches(matches).filter(match => (
    (filters.mode === 'all' || profileMode(match) === filters.mode)
    && (filters.season === 'all' || match.season === filters.season)
    && (filters.agent === 'all' || profileAgent(match, riotId) === filters.agent)
    && (filters.map === 'all' || valorantMapName(match.map) === filters.map)
  ))
}

const valid = (value: unknown): value is number => typeof value === 'number' && Number.isFinite(value) && value >= 0
const sum = (values: number[]) => values.reduce((total, value) => total + value, 0)
const ratio = (numerator: number | undefined, denominator: number | undefined) => numerator != null && denominator != null && denominator > 0 ? numerator / denominator : undefined
const numeric = (stats: PlayerStats, key: keyof PlayerStats): number | undefined => valid(stats[key]) ? stats[key] as number : undefined

/** Every numerator and denominator use the same evidence window. No average of averages. */
export function aggregateProfile(matches: Match[], riotId: string) {
  const stats = matches.map(match => profilePlayer(match, riotId)?.stats).filter((value): value is PlayerStats => Boolean(value))
  const total = (key: keyof PlayerStats) => {
    const values = stats.map(row => numeric(row, key)).filter((value): value is number => value != null)
    return values.length ? sum(values) : undefined
  }
  const rate = (numerator: keyof PlayerStats, denominator: keyof PlayerStats) => {
    const samples = stats.filter(row => numeric(row, numerator) != null && valid(row[denominator]) && (row[denominator] as number) > 0)
    return ratio(sum(samples.map(row => numeric(row, numerator)!)), sum(samples.map(row => numeric(row, denominator)!)))
  }
  const kda = stats.filter(row => [row.kills, row.deaths, row.assists].every(valid))
  const kills = kda.length ? sum(kda.map(row => row.kills!)) : undefined
  const deaths = kda.length ? sum(kda.map(row => row.deaths!)) : undefined
  const assists = kda.length ? sum(kda.map(row => row.assists!)) : undefined
  const shots = stats.filter(row => [row.headshots, row.bodyshots, row.legshots].every(valid))
  const headshots = shots.length ? sum(shots.map(row => row.headshots!)) : undefined
  const bodyshots = shots.length ? sum(shots.map(row => row.bodyshots!)) : undefined
  const legshots = shots.length ? sum(shots.map(row => row.legshots!)) : undefined
  const hits = shots.length ? headshots! + bodyshots! + legshots! : undefined
  const results = matches.map(match => match.result.toLowerCase())
  const wins = results.filter(result => ['win', 'victory'].includes(result)).length
  const losses = results.filter(result => ['loss', 'defeat'].includes(result)).length
  const draws = results.filter(result => ['draw', 'tie'].includes(result)).length
  const delta = stats.filter(row => [row.damage, row.damageReceived, row.roundsPlayed].every(valid) && row.roundsPlayed! > 0)
  const scored = matches.flatMap(match => {
    if (match.freeForAll || !['competitive', 'unrated', 'swiftplay', 'spikerush', 'premier'].includes(profileMode(match))) return []
    const own = profilePlayer(match, riotId)
    const ownTeam = match.teams?.find(team => own && team.players.includes(own))
    if (!ownTeam || match.teams?.length !== 2 || !match.teams.every(team => valid(team.score))) return []
    return [{won: ownTeam.score as number, played: sum(match.teams.map(team => team.score as number))}]
  })
  const durations = matches.map(match => match.durationSeconds).filter((value): value is number => valid(value))
  const weapons = new Map<string, number>()
  let weaponMatches = 0
  for (const row of stats) {
    if (!row.weaponUsage) continue
    weaponMatches++
    for (const weapon of row.weaponUsage) {
      if (valid(weapon.kills)) weapons.set(weapon.weapon, (weapons.get(weapon.weapon) ?? 0) + weapon.kills)
    }
  }
  const weaponKills = sum([...weapons.values()])
  const kast = rate('kastRounds', 'impactRounds')
  const hs = ratio(headshots, hits)
  const winRate = ratio(wins, wins + losses + draws)
  const roundWinRate = ratio(sum(scored.map(row => row.won)), sum(scored.map(row => row.played)))
  return {
    matches: matches.length, detailed: kda.length, wins, losses, draws,
    kills, deaths, assists, kd: ratio(kills, deaths), kad: ratio(kills != null && assists != null ? kills + assists : undefined, deaths),
    winRate: winRate != null ? winRate * 100 : undefined,
    acs: rate('combatScore', 'roundsPlayed'), adr: rate('damage', 'roundsPlayed'),
    damageDelta: ratio(sum(delta.map(row => row.damage! - row.damageReceived!)), sum(delta.map(row => row.roundsPlayed!))),
    kast: kast != null ? kast * 100 : undefined,
    headshotRate: hs != null ? hs * 100 : undefined, headshots, bodyshots, legshots, hits,
    firstKills: total('firstKills'), firstDeaths: total('firstDeaths'), aces: total('aces'), flawless: total('flawlessRounds'),
    killsPerRound: rate('kills', 'roundsPlayed'), rounds: total('roundsPlayed'),
    roundWinRate: roundWinRate != null ? roundWinRate * 100 : undefined,
    seconds: durations.length ? sum(durations) : undefined,
    weaponMatches,
    weapons: [...weapons].map(([label, count]) => ({label, kills: count, share: weaponKills ? count / weaponKills * 100 : 0})).sort((a, b) => b.kills - a.kills),
    coverage: {
      acs: stats.filter(row => valid(row.combatScore) && valid(row.roundsPlayed) && row.roundsPlayed > 0).length,
      adr: stats.filter(row => valid(row.damage) && valid(row.roundsPlayed) && row.roundsPlayed > 0).length,
      kast: stats.filter(row => valid(row.kastRounds) && valid(row.impactRounds) && row.impactRounds > 0).length,
      damageDelta: delta.length, shots: shots.length, duration: durations.length,
      rounds: scored.length,
      firstKills: stats.filter(row => valid(row.firstKills)).length,
      firstDeaths: stats.filter(row => valid(row.firstDeaths)).length,
      flawless: stats.filter(row => valid(row.flawlessRounds)).length,
      aces: stats.filter(row => valid(row.aces)).length,
    },
  }
}

export function profileBreakdown(matches: Match[], riotId: string, by: 'agent' | 'map' | 'role') {
  const groups = new Map<string, Match[]>()
  for (const match of matches) {
    const key = by === 'agent' ? profileAgent(match, riotId) : by === 'map' ? valorantMapName(match.map) : profileRole(match, riotId)
    groups.set(key, [...(groups.get(key) ?? []), match])
  }
  return [...groups].map(([label, entries]) => ({label, ...aggregateProfile(entries, riotId)}))
    .sort((a, b) => b.matches - a.matches || b.wins - a.wins || a.label.localeCompare(b.label))
}
