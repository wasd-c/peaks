import {profileMatches, profilePlayer} from './accountProfile'
import {gameMode, tftPositivePlacement, validTftPlacement} from './riotProfile'
import type {Match} from './types'

/** Omit the filter for the most recent TFT games across every queue. */
export function tftRecentResults(matches: Match[], riotId: string, duos?: boolean) {
  const now = Date.now()
  const all = profileMatches(matches, 'Teamfight Tactics').filter(match => duos == null || (gameMode(match) === 'Double Up') === duos)
  const ordered = all.filter(match => typeof match.playedAtTimestamp === 'number'
    && Number.isFinite(match.playedAtTimestamp) && match.playedAtTimestamp > 0
    && match.playedAtTimestamp <= now)
  const rows = ordered.map(match => {
    const value = profilePlayer(match, riotId)?.stats?.placement
    const placement = validTftPlacement(value) ? value : undefined
    const positivePlacement = tftPositivePlacement(match)
    const positive = placement != null && positivePlacement != null ? placement <= positivePlacement : undefined
    return {match, placement, positive, positivePlacement}
  })

  // Missing timestamps cannot establish chronology; missing placements interrupt
  // a streak instead of silently joining the results on either side of them.
  let streak: number | undefined
  if (ordered.length === all.length && rows[0]?.positive != null) {
    const positive = rows[0].positive
    streak = 0
    for (const row of rows) {
      if (row.positive == null || row.positive !== positive) break
      streak += positive ? 1 : -1
    }
  }
  return {rows: rows.slice(0, 20), streak}
}
