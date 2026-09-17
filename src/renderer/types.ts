export type Game = 'League of Legends' | 'VALORANT' | 'Teamfight Tactics'

export interface Rank {
  game: Game
  tier: string
  division?: string
  rating?: number
  icon?: string
}

export interface PlayerStats {
  kills?: number
  deaths?: number
  assists?: number
  combatScore?: number
  roundsPlayed?: number
  headshots?: number
  bodyshots?: number
  legshots?: number
  damage?: number
  gold?: number
  minions?: number
  vision?: number
  level?: number
  placement?: number
  playersEliminated?: number
  /** Current tactician HP supplied by a live TFT source; never a postgame value. */
  health?: number
  /** Periodic TFT snapshot, never a final placement while the match is active. */
  standing?: number
  boardUnits?: number
  augmentCount?: number
  /** Source snapshot Unix time in seconds; does not imply frame-by-frame updates. */
  observedAt?: number
  /** Bounded recent history; these fields never imply lifetime coverage. */
  matchesPlayed?: number
  wins?: number
  scope?: 'recent'
  source?: 'authenticated-client-history'
  /** Newest-first per-game evidence; aggregates alone cannot prove a streak. */
  recentKda?: Array<{kills: number; deaths: number}>
  /** Actual weapon kill counts from detailed match events. */
  weaponUsage?: Array<{weapon: string; kills: number}>
  /** Each entry is the player's elimination count in one recorded round. */
  roundKills?: number[]
  /** Complete event rounds, excluding explicit event-empty surrender awards. */
  roundsAnalyzed?: number
}

export interface MatchPlayer {
  name: string
  riotId?: string
  region?: string
  rank?: string
  rankTier?: number
  currentRank?: string
  currentRankTier?: number
  peakRank?: string
  peakRankTier?: number
  peakRankSeason?: string
  accountLevel?: number
  /** Presentation-only grouping key, never the raw Riot party identifier. */
  partyId?: string
  /** Only supplied when the connected client exposes the lobby state. */
  ready?: boolean
  leader?: boolean
  role?: string
  agent?: string
  score?: string
  stats?: PlayerStats
  /** Historical totals, kept separate from this match's evidence. */
  overallStats?: PlayerStats
  /** True only while the backend is fetching eligible player statistics. */
  statsLoading?: boolean
  self?: boolean
  hidden?: boolean
}

export interface MatchTeam {
  name: string
  /** Verified Double Up pair, or players whose pairing is not exposed. */
  grouping?: 'duo' | 'unassigned'
  score?: number | string | null
  won?: boolean | null
  players: MatchPlayer[]
}

export interface Match {
  id?: string
  game: Game
  result: string
  mode?: string
  map?: string
  agent?: string
  score?: string
  playedAt?: string
  duration?: string
  delta?: string
  performance?: string
  positive?: boolean
  freeForAll?: boolean
  teamMode?: 'duos'
  enrichmentPending?: boolean
  teams?: MatchTeam[]
}

export interface PlayerContext {
  label: string
  matchId?: string
  map?: string
  result?: string
  team?: string
  character?: string
  score?: string
  stats?: PlayerStats
}

export interface Player {
  id: string
  riotId: string
  region: string
  currentRank?: string
  peakRank?: string
  game?: Game
  games?: Game[]
  followed?: boolean
  lastGame?: string
  lastUpdated?: string
  initials?: string
  level?: number
  ranks?: Rank[]
  matches?: Match[]
  context?: PlayerContext
}

export interface Account {
  id: string
  riotId: string
  region: string
  level?: number
  avatar?: string
  ranks: Rank[]
  peakRanks?: Rank[]
  matches?: Match[]
  hasTotp?: boolean
  connected?: boolean
  canConnectQr?: boolean
  canSaveRiotSession?: boolean
  canSetupMfa?: boolean
  owned?: boolean
  initials?: string
  lastUpdated?: string
}

export type SessionPhase = 'lobby' | 'matchmaking' | 'readycheck' | 'pregame' | 'live'

export interface CurrentMatch {
  freeForAll?: boolean
  teamMode?: 'duos'
  queue?: string
  modeId?: string
  /** Authenticated party membership, independent of team size. */
  partySize?: number
  partyMax?: number
  id?: string
  phase?: SessionPhase
  accountId?: string
  isStale?: boolean
  game?: Game
  map?: string
  mode?: string
  elapsed?: string
  status?: string
  streamerMode?: boolean
  privacyNote?: string
  artwork?: string
  teams?: MatchTeam[]
}

export interface Settings {
  autoLockMinutes: number
  streamerMode?: boolean
  lockOnBlur: boolean
  reduceMotion: boolean
  riotApiConfigured: boolean
  clipboardClearSeconds: number
}

export interface AppState {
  locked: boolean
  hasPasscode: boolean
  pinMode: 'create' | 'confirm' | 'unlock'
  pinError: string
  accounts: Account[]
  followed: Player[]
  searchHistory: string[]
  currentMatch: CurrentMatch
  gameDetected: boolean
  settings: Settings
  riotClient: {detected: boolean; label: string; game?: string}
  operationNotice?: string
}

export interface TotpSetupProposal {
  confirmationId: string
  accountId: string
  riotId: string
  expiresInSeconds: number
}

export interface TotpSetupResult {
  state: AppState
  seedSaved: boolean
  verified: boolean
  warning?: string | null
}

declare global {
  interface Window {
    peaks?: {invoke<T>(command: string, payload?: unknown): Promise<T>}
  }
}
