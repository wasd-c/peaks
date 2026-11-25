import {formatNumber} from './i18n'
import type {Game, PlayerStats} from './types'

export const validNumber = (value: unknown): value is number => typeof value === 'number' && Number.isFinite(value) && value >= 0
export const hasNumbers = (stats?: PlayerStats) => Boolean(stats && Object.entries(stats).some(([key, value]) => !['matchesPlayed', 'wins', 'observedAt'].includes(key) && validNumber(value)))
export const numeric = (value?: number, decimals = 0) => validNumber(value) ? formatNumber(value, {maximumFractionDigits: decimals}) : '—'
export const average = (value?: number, count?: number) => validNumber(value) ? numeric(count && count > 0 ? value / count : value, count && count > 1 ? 1 : 0) : '—'
const ratio = (numerator?: number, denominator?: number, decimals = 0) => validNumber(numerator) && validNumber(denominator) && denominator > 0 ? numeric(numerator / denominator, decimals) : '—'

function headshotRate(stats?: PlayerStats) {
  if (!stats || ![stats.headshots, stats.bodyshots, stats.legshots].every(validNumber)) return '—'
  const hits = stats.headshots! + stats.bodyshots! + stats.legshots!
  return hits > 0 ? `${Math.round(stats.headshots! / hits * 100)}%` : '—'
}

export function statsRows(overall?: PlayerStats, match?: PlayerStats, preserveRowsFor?: Game) {
  const count = overall?.matchesPlayed
  const rows = [
    {label: 'HP', overall: '—', match: numeric(match?.health, 1)},
    {label: 'Standing', overall: '—', match: validNumber(match?.standing) ? `#${numeric(match.standing)}` : '—'},
    {label: 'Board units', overall: '—', match: numeric(match?.boardUnits)},
    {label: 'Augments', overall: '—', match: numeric(match?.augmentCount)},
    {label: 'K/D', overall: ratio(overall?.kills, overall?.deaths, 2), match: ratio(match?.kills, match?.deaths, 2)},
    {label: 'ACS', overall: ratio(overall?.combatScore, overall?.roundsPlayed), match: ratio(match?.combatScore, match?.roundsPlayed)},
    {label: 'ADR', overall: ratio(overall?.damage, overall?.roundsPlayed), match: ratio(match?.damage, match?.roundsPlayed)},
    {label: 'HS%', overall: headshotRate(overall), match: headshotRate(match)},
    ...(['kills', 'deaths', 'assists'] as const).map(key => ({label: `${key[0].toUpperCase()}${key.slice(1)}`, overall: average(overall?.[key], count), match: numeric(match?.[key])})),
    ...([
      ['gold', 'Gold'], ['minions', 'CS'], ['vision', 'Vision'], ['placement', 'Placement'], ['playersEliminated', 'Eliminations'], ['level', 'Level'],
    ] as const).map(([key, label]) => ({label, overall: average(overall?.[key], count), match: numeric(match?.[key])})),
  ]
  if ((overall?.combatScore != null && !overall.roundsPlayed) || (match?.combatScore != null && !match.roundsPlayed)) {
    rows.push({label: 'Score', overall: !overall?.roundsPlayed ? average(overall?.combatScore, count) : '—', match: !match?.roundsPlayed ? numeric(match?.combatScore) : '—'})
  }
  if ((overall?.damage != null && !overall.roundsPlayed) || (match?.damage != null && !match.roundsPlayed)) {
    rows.push({label: 'Damage', overall: !overall?.roundsPlayed ? average(overall?.damage, count) : '—', match: !match?.roundsPlayed ? numeric(match?.damage) : '—'})
  }
  const reservedLabels = preserveRowsFor === 'VALORANT' ? ['K/D', 'ACS', 'ADR', 'HS%', 'Kills', 'Deaths', 'Assists']
    : preserveRowsFor === 'League of Legends' ? ['K/D', 'Kills', 'Deaths', 'Assists', 'Gold', 'CS', 'Vision']
      : preserveRowsFor === 'Teamfight Tactics' ? ['Placement', 'Eliminations', 'Gold', 'Level'] : []
  return rows.filter(row => reservedLabels.includes(row.label) || row.overall !== '—' || row.match !== '—')
}
