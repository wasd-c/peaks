import type {Account, Match, MatchPlayer} from './types'
import {historicalPerformanceTags, playerPerformanceTags} from './matchAnalytics'

export interface MatchShareTag {
  label: string
  source: 'match' | 'history'
}

export interface MatchShareSummary {
  game: Match['game']
  result: string
  map?: string
  mode: string
  score: string
  duration: string
  tags: MatchShareTag[]
  playerName?: string
  character?: string
  kda?: string
  combatScore?: string
  damagePerRound?: string
}

const identity = (value: string) => value.trim().toLocaleLowerCase()

function visibleOwner(match: Match, account?: Pick<Account, 'riotId'>): MatchPlayer | undefined {
  const players = (match.teams ?? []).flatMap(team => team.players)
  const selected = account
    ? players.find(player => identity(player.riotId ?? player.name) === identity(account.riotId))
    : players.find(player => player.self)
  return selected?.hidden ? undefined : selected
}

function shareTags(player: MatchPlayer | undefined, game: Match['game']): MatchShareTag[] {
  if (!player) return []
  const tags: MatchShareTag[] = []
  const labels = new Set<string>()
  const sources = [
    ['match', playerPerformanceTags(player, game)],
    ['history', historicalPerformanceTags(player, game)],
  ] as const
  for (const [source, observations] of sources) {
    for (const observation of observations) {
      const label = observation.label.trim()
      const key = identity(label)
      if (!label || label.length > 64 || labels.has(key)
        || Array.from(label).some(character => character.charCodeAt(0) < 32
          || (character.charCodeAt(0) >= 127 && character.charCodeAt(0) < 160))) continue
      tags.push({label, source})
      labels.add(key)
      if (tags.length === 4) return tags
    }
  }
  return tags
}

/** Deliberately copy only the fields that belong on a public match image. */
export function matchShareSummary(
  match: Match, account?: Pick<Account, 'riotId'>,
  displayName: (identity: string) => string = identity => identity,
): MatchShareSummary {
  const player = visibleOwner(match, account)
  const stats = player?.stats
  const rounds = stats?.roundsPlayed
  const hasKda = stats && [stats.kills, stats.deaths, stats.assists].some(value => value != null)
  return {
    game: match.game,
    result: match.result,
    map: match.map,
    mode: match.mode ?? 'Match',
    score: match.score ?? '—',
    duration: match.duration ?? '—',
    tags: shareTags(player, match.game),
    playerName: player ? displayName(player.riotId ?? player.name) : undefined,
    character: player?.agent,
    kda: hasKda
      ? `${stats.kills ?? '—'} / ${stats.deaths ?? '—'} / ${stats.assists ?? '—'}`
      : player?.score,
    combatScore: stats?.combatScore != null && rounds != null && rounds > 0
      ? String(Math.round(stats.combatScore / rounds))
      : undefined,
    damagePerRound: stats?.damage != null && rounds != null && rounds > 0
      ? String(Math.round(stats.damage / rounds))
      : undefined,
  }
}

export function matchShareCaption(summary: MatchShareSummary, map: string): string {
  return `${summary.result} on ${map} · ${summary.score}${summary.kda ? ` · ${summary.kda} K/D/A` : ''}\n${summary.game} match recap, made with Peaks.`
}

export function matchShareFilename(summary: MatchShareSummary): string {
  const slug = `${summary.game}-${summary.map ?? 'match'}-${summary.result}`
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-|-$/g, '')
  return `peaks-${slug}.png`
}
