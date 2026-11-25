import {findAccountIcon} from './accountIcons'
import {profilePlayer} from './accountProfile'
import {tftPositivePlacement, validTftPlacement} from './riotProfile'
import type {Match, MatchPlayer} from './types'

export interface MatchHistoryRow {
  character?: {name: string; image: string}
  result: 'Victory' | 'Defeat' | 'Draw' | 'Unknown'
  score?: string
  placement?: number
  rank?: string
  rankTier?: number
  delta?: number
  deltaUnit?: 'RR' | 'LP'
}

const identity = (value: string) => value.trim().toLocaleLowerCase('en')
const count = (value: unknown): value is number => typeof value === 'number' && Number.isSafeInteger(value) && value >= 0
const scoreValue = (value: unknown): number | undefined => count(value) ? value : typeof value === 'string' && /^\d+$/.test(value.trim()) && count(Number(value)) ? Number(value) : undefined

function selectedPlayer(match: Match, riotId?: string): MatchPlayer | undefined {
  const target = riotId?.trim()
  const player = profilePlayer(match, target ?? '')
  // Unlike the account profile, a report may be viewed for a different player.
  // A mismatched self marker is not evidence of that visitor's identity.
  return target && player && identity(player.riotId ?? player.name) !== identity(target) ? undefined : player
}

function rankedMode(match: Match): boolean {
  const mode = (match.mode ?? '').trim().toLocaleLowerCase('en')
  if (match.freeForAll && match.game !== 'Teamfight Tactics') return false
  if (match.game === 'VALORANT') return mode === 'competitive'
  if (match.game === 'League of Legends') return new Set(['420', '440', 'ranked solo', 'ranked solo / duo', 'ranked solo/duo', 'ranked flex', 'ranked_solo_5x5', 'ranked_flex_sr']).has(mode)
  return new Set(['1100', '1150', '1160', 'ranked', 'ranked_tft', 'pairs', 'double up', 'ranked_tft_double_up']).has(mode)
}

function resultName(value: string): MatchHistoryRow['result'] {
  const normalized = value.trim().toLocaleLowerCase('en')
  if (['win', 'victory'].includes(normalized)) return 'Victory'
  if (['loss', 'defeat'].includes(normalized)) return 'Defeat'
  if (['draw', 'tie'].includes(normalized)) return 'Draw'
  return 'Unknown'
}

function rankReward(value: string | undefined, unit: 'RR' | 'LP'): number | undefined {
  if (!value) return undefined
  const parsed = /^([+-]?\d+)\s*(RR|LP)?$/i.exec(value.trim().replace(/^−/, '-'))
  if (!parsed || (parsed[2] && parsed[2].toUpperCase() !== unit)) return undefined
  const reward = Number(parsed[1])
  return Number.isSafeInteger(reward) && Math.abs(reward) <= 1_000 ? reward : undefined
}

/** Match evidence only: never current rank, aggregate KDA, or inferred LP/RR. */
export function matchHistoryRow(match: Match, riotId?: string): MatchHistoryRow {
  const player = selectedPlayer(match, riotId)
  const players = (match.teams ?? []).flatMap(team => team.players)
  const selves = players.filter(candidate => candidate.self)
  const ownerBound = (selves.length === 1 && selves[0] === player) || (!riotId?.trim() && players.length === 0)
  const row: MatchHistoryRow = {result: ownerBound ? resultName(match.result) : 'Unknown'}
  const ownTeam = player ? match.teams?.find(team => team.players.includes(player)) : undefined

  if (match.game === 'Teamfight Tactics') {
    const positivePlacement = tftPositivePlacement(match)
    const provided = player?.stats?.placement
    const summaryPlacement = ownerBound && /^#?[1-8]$/.test(match.score?.trim() ?? '') ? Number(match.score!.trim().replace('#', '')) : undefined
    const placement = provided ?? summaryPlacement
    if (validTftPlacement(placement)) {
      row.placement = placement
      row.result = positivePlacement == null ? 'Unknown' : placement <= positivePlacement ? 'Victory' : 'Defeat'
    }
  } else {
    const characterId = player?.agent || (ownerBound ? match.agent : undefined)
    const character = characterId ? findAccountIcon({game: match.game, characterId}) : undefined
    if (character) row.character = {name: character.name, image: character.image}

    if (ownTeam?.won != null) row.result = ownTeam.won ? 'Victory' : 'Defeat'
    if (match.game === 'League of Legends') {
      const stats = player?.stats
      if (count(stats?.kills) && count(stats?.deaths) && count(stats?.assists)) row.score = `${stats.kills}/${stats.deaths}/${stats.assists}`
    } else if (!match.freeForAll) {
      const opponent = match.teams?.length === 2 && ownTeam ? match.teams.find(team => team !== ownTeam) : undefined
      const ownScore = scoreValue(ownTeam?.score), opponentScore = scoreValue(opponent?.score)
      if (ownScore != null && opponentScore != null) {
        row.score = `${ownScore}-${opponentScore}`
        if (ownScore === opponentScore && ownTeam?.won !== true && opponent?.won !== true) row.result = 'Draw'
        else if (ownTeam?.won == null) row.result = ownScore > opponentScore ? 'Victory' : 'Defeat'
      } else if (ownerBound) {
        const score = /^\s*(\d+)\s*[:—–-]\s*(\d+)\s*$/.exec(match.score ?? '')
        if (score && count(Number(score[1])) && count(Number(score[2]))) row.score = `${Number(score[1])}-${Number(score[2])}`
      }
    }
  }

  if (rankedMode(match)) {
    const historicalRank = player?.rank?.trim()
    if (historicalRank && !['unknown', '—', '-'].includes(historicalRank.toLocaleLowerCase('en'))) {
      row.rank = historicalRank
    }
    if (match.game === 'VALORANT' && count(player?.rankTier) && player.rankTier >= 3 && player.rankTier <= 27) row.rankTier = player.rankTier
    const unit = match.game === 'VALORANT' ? 'RR' : 'LP'
    const reward = ownerBound ? rankReward(match.delta, unit) : undefined
    if (reward != null) { row.delta = reward; row.deltaUnit = unit }
  }
  return row
}
