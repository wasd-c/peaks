import type {Game, MatchTeam, SessionPhase} from './types'

export interface MatchLayoutInput {
  teams: readonly MatchTeam[]
  game?: Game
  mode?: string
  /** Native queue identifier, when the source provides one. */
  queueId?: string
  modeId?: string
  /** Native game-mode asset path, when the source provides one. */
  gameMode?: string
  /** An explicit source classification takes precedence over display labels. */
  freeForAll?: boolean
  teamMode?: 'duos'
  phase?: SessionPhase
}

export interface MatchLayout {
  kind: 'free-for-all' | 'teams' | 'roster' | 'duos'
  groups: MatchTeam[]
  canAlignRoles: boolean
}

const modeKey = (value?: string) => value?.trim().toLowerCase().replace(/[^a-z0-9]/g, '') ?? ''
const FREE_FOR_ALL_MODES = new Set(['deathmatch', 'freeforall', 'ffa'])
const DOUBLE_UP_MODES = new Set([
  '1150', '1160', 'doubleup', 'tftdoubleup', 'doubleupworkshop',
  'tftdoubleupworkshop', 'tftdoubleupbeta', 'tftpairs', 'pairs',
  'rankedtftdoubleup', 'rankedtftpairs',
])

function modeIsDoubleUp(input: MatchLayoutInput): boolean {
  if (input.game !== 'Teamfight Tactics') return false
  if (input.teamMode === 'duos') return true
  const queue = input.queueId?.trim() ?? ''
  // An actual queue ID wins over a stale or broad display label. Older reports
  // retained the queue only as their mode string, so accept that as a fallback.
  if (/^\d+$/.test(queue)) return queue === '1150' || queue === '1160'
  return [queue, input.mode, input.modeId, input.gameMode].some(value => DOUBLE_UP_MODES.has(modeKey(value)))
}

/** A lobby size or adjacent player order is never evidence of a duo. */
export function isConfirmedDuo(team: MatchTeam): boolean {
  return team.players.length > 0 && team.players.length <= 2
    && (team.grouping === 'duo' || (team.grouping === undefined && /^Duo\s+\d+$/i.test(team.name.trim())))
}

function deathmatchMode(value?: string): boolean {
  const asset = value?.split('/').at(-1)?.split('.')[0]
  return FREE_FOR_ALL_MODES.has(modeKey(value)) || modeKey(asset) === 'deathmatchgamemode'
}

function modeIsFreeForAll(input: MatchLayoutInput): boolean {
  // A party is a roster of friends, even when the selected queue is solo FFA.
  if (input.phase && ['lobby', 'matchmaking', 'readycheck'].includes(input.phase)) return false
  if (input.freeForAll !== undefined) return input.freeForAll
  if (input.game !== 'VALORANT') return false
  // A queue ID is more specific than a display name. In particular, do not
  // classify Team Deathmatch (hurm) from a broad "deathmatch" substring.
  if (input.queueId?.trim()) return FREE_FOR_ALL_MODES.has(modeKey(input.queueId))
  const modeId = input.modeId ?? input.gameMode
  if (modeId?.trim()) return deathmatchMode(modeId)
  return deathmatchMode(input.mode)
}

/** Keep the source's team boundaries; mode names never invent teams or sizes. */
export function resolveMatchLayout(input: MatchLayoutInput): MatchLayout {
  // Older TFT snapshots classified every queue as FFA. Preserve Double Up's
  // real pairs before considering that legacy classification.
  if (modeIsDoubleUp(input)) {
    const pairs = input.teams.filter(isConfirmedDuo)
    const unassigned = input.teams.filter(team => !isConfirmedDuo(team)).flatMap(team => team.players)
    return {
      kind: 'duos',
      groups: [...pairs, ...(unassigned.length ? [{name: 'Players', grouping: 'unassigned' as const, players: unassigned}] : [])],
      canAlignRoles: false,
    }
  }
  if (modeIsFreeForAll(input)) {
    const players = input.teams.flatMap(team => team.players)
    return {
      kind: 'free-for-all',
      groups: players.length ? [{name: input.game === 'Teamfight Tactics' ? 'Players' : 'Free for all', players}] : [],
      canAlignRoles: false,
    }
  }

  const groups = [...input.teams]
  const equallySizedTeams = groups.length === 2
    && groups[0].players.length > 0
    && groups[0].players.length === groups[1].players.length
  return {
    kind: groups.length > 1 ? 'teams' : 'roster',
    groups,
    // Only two equally sized rows can form a visual role-v-role comparison.
    // Keep combinatorial matching bounded for future modes and custom lobbies.
    canAlignRoles: input.game === 'VALORANT' && equallySizedTeams && groups[0].players.length <= 5,
  }
}

/** Only bounded team rosters can occupy two fixed rows without losing players. */
export function fitsValorantRoster(input: MatchLayoutInput): boolean {
  const layout = resolveMatchLayout(input)
  return input.game === 'VALORANT' && layout.kind === 'teams' && layout.groups.length === 2
    && layout.groups.every(team => team.players.length > 0 && team.players.length <= 5)
}

/** Structural width belongs to Astryx Grid; CSS does not override its tracks. */
export function matchGridColumns(playerCount: number, game?: Game): {minWidth: number; max: number; repeat: 'fit'} {
  const count = Number.isFinite(playerCount) ? Math.max(1, Math.floor(playerCount)) : 1
  const limit = game === 'Teamfight Tactics' && count === 8 ? 4 : 6
  return {minWidth: 180, max: Math.min(limit, count), repeat: 'fit'}
}
