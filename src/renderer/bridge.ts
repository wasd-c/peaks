import type {Account, AccountIconSelection, AppState, Game, MatchPlayer, MatchTeam, Player, PlayerStats, TotpSetupProposal, TotpSetupResult} from './types'
import {samePlayerIdentity} from './playerProfiles'

export const RESET_APPLICATION_CONFIRMATION = 'clear-encrypted-data'

const valorantMatchTeams: MatchTeam[] = [
  {
    name: 'Your team',
    score: 13,
    won: true,
    players: [
      {
        name: 'Aurélïne#EUW',
        riotId: 'Aurélïne#EUW',
        agent: 'Omen',
        rank: 'Ascendant 2',
        rankTier: 22,
        score: '24 / 13 / 6',
        stats: {kills: 24, deaths: 13, assists: 6, combatScore: 6678, roundsPlayed: 21, headshots: 19, bodyshots: 39, legshots: 3, damage: 4982},
        self: true,
      },
      {
        name: 'dusk#EU',
        riotId: 'dusk#EU',
        agent: 'Sova',
        rank: 'Diamond 3',
        rankTier: 20,
        score: '18 / 14 / 11',
        stats: {kills: 18, deaths: 14, assists: 11, combatScore: 5124, roundsPlayed: 21, headshots: 12, bodyshots: 34, legshots: 2, damage: 3916},
      },
      {
        name: 'zephyr#WIND',
        riotId: 'zephyr#WIND',
        agent: 'Jett',
        rank: 'Ascendant 1',
        rankTier: 21,
        score: '16 / 15 / 4',
        stats: {kills: 16, deaths: 15, assists: 4},
      },
      {name: 'lumen#soft', riotId: 'lumen#soft', agent: 'Sage', rank: 'Diamond 2', rankTier: 19, score: '12 / 11 / 14', stats: {kills: 12, deaths: 11, assists: 14, combatScore: 4032, roundsPlayed: 21}},
      {name: 'solstice#EU', riotId: 'solstice#EU', agent: 'Raze', rank: 'Ascendant 1', rankTier: 21, score: '19 / 14 / 7', stats: {kills: 19, deaths: 14, assists: 7, combatScore: 5523, roundsPlayed: 21}},
    ],
  },
  {
    name: 'Opponents',
    score: 8,
    won: false,
    players: [
      {
        name: 'nova#ACE',
        riotId: 'nova#ACE',
        agent: 'Reyna',
        rank: 'Ascendant 3',
        rankTier: 23,
        score: '21 / 17 / 3',
        stats: {kills: 21, deaths: 17, assists: 3, combatScore: 6006, roundsPlayed: 21, headshots: 16, bodyshots: 31, legshots: 4, damage: 4221},
      },
      {
        name: 'calm#000',
        riotId: 'calm#000',
        agent: 'Cypher',
        rank: 'Diamond 2',
        rankTier: 19,
        score: '12 / 19 / 8',
        stats: {kills: 12, deaths: 19, assists: 8},
      },
      {name: 'vanta#VENOM', riotId: 'vanta#VENOM', agent: 'Viper', rank: 'Ascendant 2', rankTier: 22, score: '15 / 18 / 7', stats: {kills: 15, deaths: 18, assists: 7, combatScore: 4389, roundsPlayed: 21}},
      {name: 'atlas#EU', riotId: 'atlas#EU', agent: 'Breach', rank: 'Diamond 3', rankTier: 20, score: '11 / 18 / 12', stats: {kills: 11, deaths: 18, assists: 12, combatScore: 3381, roundsPlayed: 21}},
      {name: 'echo#808', riotId: 'echo#808', agent: 'Fade', rank: 'Ascendant 1', rankTier: 21, score: '8 / 19 / 6', stats: {kills: 8, deaths: 19, assists: 6, combatScore: 2730, roundsPlayed: 21}},
    ],
  },
]

// Synthetic browser fixtures only. Native data always comes from the Python bridge.
valorantMatchTeams.forEach((team, teamIndex) => {
  team.players = team.players.map((player, index) => ({
    ...player,
    accountLevel: [284, 197, 163, 326, 211][index],
    currentRank: player.rank,
    currentRankTier: player.rankTier,
    peakRank: ['Immortal 1', 'Ascendant 3', 'Immortal 2', 'Ascendant 2', 'Immortal 1'][index],
    peakRankTier: [24, 23, 25, 22, 24][index],
    peakRankSeason: ['V26:A1', 'E9:A3', 'V25:A6', 'E8:A2', 'V26:A2'][index],
    partyId: index < 2 ? `party-${teamIndex + 1}` : undefined,
    overallStats: {
      matchesPlayed: 5, wins: [4, 3, 2, 4, 3][index], scope: 'recent', source: 'authenticated-client-history',
      kills: [106, 89, 94, 62, 101][index], deaths: [73, 71, 86, 68, 77][index], assists: [32, 47, 23, 61, 30][index],
      roundsPlayed: 112, combatScore: [28672, 25536, 27104, 19264, 28224][index],
      headshots: [92, 67, 112, 43, 80][index], bodyshots: [161, 164, 176, 141, 166][index], legshots: [10, 16, 14, 17, 13][index],
      damage: [17360, 15680, 18368, 12656, 17920][index],
    },
  }))
})

// Five individually recorded rough games demonstrate the historical banter tag.
valorantMatchTeams[1].players[1].overallStats = {
  matchesPlayed: 5, wins: 1, scope: 'recent', source: 'authenticated-client-history',
  kills: 40, deaths: 94, assists: 20, roundsPlayed: 112, combatScore: 10000,
  headshots: 8, bodyshots: 96, legshots: 16, damage: 8960,
  recentKda: [{kills: 10, deaths: 20}, {kills: 7, deaths: 18}, {kills: 9, deaths: 19}, {kills: 8, deaths: 17}, {kills: 6, deaths: 20}],
}

// Rich synthetic event evidence belongs only to the first browser preview match.
const firstValorantMatchTeams: MatchTeam[] = valorantMatchTeams.map(team => ({
  ...team,
  players: team.players.map(player => {
    if (player.self) return {
      ...player,
      stats: {
        ...player.stats,
        combatScore: 6678,
        roundsPlayed: 21,
        headshots: 19,
        bodyshots: 39,
        legshots: 3,
        damage: 4982,
        roundKills: [1, 0, 2, 1, 3, 0, 1, 1, 0, 2, 1, 1, 2, 0, 1, 2, 1, 0, 2, 1, 2],
        weaponUsage: [{weapon: 'Vandal', kills: 14}, {weapon: 'Ghost', kills: 6}, {weapon: 'Phantom', kills: 4}],
      },
    }
    if (player.riotId === 'nova#ACE') return {
      ...player,
      stats: {
        ...player.stats,
        combatScore: 6006,
        roundsPlayed: 21,
        roundKills: [1, 1, 0, 2, 1, 3, 0, 1, 1, 0, 2, 1, 1, 0, 1, 1, 1, 0, 2, 1, 1],
        weaponUsage: [{weapon: 'Phantom', kills: 15}, {weapon: 'Ghost', kills: 6}],
      },
    }
    if (player.riotId === 'calm#000') return {
      ...player,
      score: '4 / 19 / 2',
      stats: {
        kills: 4, deaths: 19, assists: 2, roundsPlayed: 21, combatScore: 1400,
        headshots: 2, bodyshots: 10, legshots: 1, damage: 760,
        roundKills: [0, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 1, 0],
        weaponUsage: [{weapon: 'Ghost', kills: 4}],
      },
    }
    return player
  }),
}))

// Synthetic in-progress evidence illustrates both tag sources in the browser demo.
// These samples never enter the native bridge or imply live scoreboard collection.
const livePreviewStats: PlayerStats[][] = [
  [
    {kills: 18, deaths: 8, assists: 5, roundsPlayed: 14, combatScore: 4410, damage: 2660, headshots: 15, bodyshots: 25, legshots: 3, roundKills: [1, 2, 1, 0, 3, 2, 1, 1, 2, 0, 1, 2, 1, 1]},
    {kills: 11, deaths: 9, assists: 11, roundsPlayed: 14, combatScore: 3136, damage: 2030, headshots: 8, bodyshots: 26, legshots: 2},
    {kills: 14, deaths: 11, assists: 3, roundsPlayed: 14, combatScore: 3626, damage: 2310, headshots: 7, bodyshots: 28, legshots: 2, weaponUsage: [{weapon: 'Operator', kills: 10}, {weapon: 'Ghost', kills: 4}]},
    {kills: 6, deaths: 9, assists: 12, roundsPlayed: 14, combatScore: 2044, damage: 1344, headshots: 3, bodyshots: 21, legshots: 2},
    {kills: 12, deaths: 11, assists: 5, roundsPlayed: 14, combatScore: 3850, damage: 2464, headshots: 8, bodyshots: 30, legshots: 4},
  ],
  [
    {kills: 16, deaths: 12, assists: 3, roundsPlayed: 14, combatScore: 4060, damage: 2590, headshots: 14, bodyshots: 24, legshots: 2},
    {kills: 3, deaths: 14, assists: 2, roundsPlayed: 14, combatScore: 896, damage: 560, headshots: 1, bodyshots: 16, legshots: 2},
    {kills: 11, deaths: 12, assists: 8, roundsPlayed: 14, combatScore: 3108, damage: 2114, headshots: 3, bodyshots: 35, legshots: 3},
    {kills: 10, deaths: 11, assists: 10, roundsPlayed: 14, combatScore: 2954, damage: 1974, headshots: 6, bodyshots: 25, legshots: 2},
    {kills: 8, deaths: 12, assists: 6, roundsPlayed: 14, combatScore: 2520, damage: 1624, headshots: 6, bodyshots: 23, legshots: 3},
  ],
]

const accounts: Account[] = [
  {
    id: 'own-aureline',
    riotId: 'Aurélïne#EUW',
    region: 'EUW',
    level: 284,
    connected: true,
    hasTotp: true,
    canConnectQr: true,
    canSaveRiotSession: true,
    canSetupMfa: false,
    owned: true,
    initials: 'AU',
    lastUpdated: 'just now',
    ranks: [
      {game: 'League of Legends', tier: 'diamond', division: 'IV', rating: 62},
      {game: 'VALORANT', tier: 'ascendant', division: '2', rating: 74},
      {game: 'Teamfight Tactics', tier: 'emerald', division: 'II', rating: 31},
    ],
    matches: [
      {id: 'v-1', game: 'VALORANT', result: 'Win', score: '13 — 8', mode: 'Competitive', map: 'Abyss', playedAt: '42 min ago', duration: '34:12', delta: '+21 RR', performance: '24 / 13 / 6 · 31% HS', positive: true, teams: firstValorantMatchTeams},
      {id: 'v-2', game: 'VALORANT', result: 'Loss', score: '10 — 13', mode: 'Competitive', map: 'Ascent', playedAt: '3h ago', delta: '-16 RR', performance: '18 / 17 / 4 · 24% HS', positive: false, teams: valorantMatchTeams},
      {id: 'v-3', game: 'VALORANT', result: 'Win', score: '13 — 4', mode: 'Competitive', map: 'Lotus', playedAt: 'yesterday', delta: '+24 RR', performance: '21 / 9 / 10 · 28% HS', positive: true, teams: valorantMatchTeams},
    ],
  },
  {
    id: 'own-peaks',
    riotId: 'peaks#0001',
    region: 'EUW',
    level: 117,
    connected: false,
    hasTotp: true,
    canConnectQr: false,
    canSaveRiotSession: true,
    canSetupMfa: false,
    owned: true,
    initials: 'PK',
    lastUpdated: '8 min ago',
    ranks: [
      {game: 'League of Legends', tier: 'emerald', division: 'I', rating: 94},
      {game: 'VALORANT', tier: 'diamond', division: '3', rating: 41},
    ],
    matches: [
      {id: 'l-1', game: 'League of Legends', agent: 'Ahri', result: 'Win', score: '32 — 21', mode: 'Ranked Solo', map: "Summoner's Rift", playedAt: '1h ago', delta: '+24 LP', performance: '8 / 2 / 11 · 7.8 CS/min', positive: true},
      {id: 'l-2', game: 'League of Legends', result: 'Loss', score: '19 — 28', mode: 'Ranked Solo', map: "Summoner's Rift", playedAt: '5h ago', delta: '-18 LP', performance: '4 / 7 / 9 · 6.9 CS/min', positive: false},
    ],
  },
  {
    id: 'own-serein',
    riotId: 'serein#quiet',
    region: 'NA',
    level: 117,
    connected: true,
    hasTotp: false,
    canConnectQr: true,
    canSaveRiotSession: true,
    canSetupMfa: true,
    owned: true,
    initials: 'SE',
    lastUpdated: 'yesterday',
    ranks: [
      {game: 'League of Legends', tier: 'platinum', division: 'II', rating: 17},
      {game: 'VALORANT', tier: 'gold', division: '2', rating: 88},
      {game: 'Teamfight Tactics', tier: 'unranked'},
    ],
    matches: [
      {id: 't-1', game: 'Teamfight Tactics', result: 'Win', score: 'Top 4', mode: 'Ranked', map: 'Current set', playedAt: '2d ago', delta: '+31 LP', performance: 'Level 9 · 5-cost board', positive: true},
    ],
  },
]

const followed: Player[] = [
  {id: 'follow-tenz', riotId: 'quietly#EUW', region: 'EUW', games: ['League of Legends', 'VALORANT'], game: 'League of Legends', currentRank: 'Immortal 2 · 112 RR', peakRank: 'Radiant #418', lastGame: '18 min ago', lastUpdated: 'Live cache', followed: true, initials: 'QU'},
  {id: 'follow-lumen', riotId: 'lumen#soft', region: 'NA', games: ['League of Legends', 'Teamfight Tactics'], game: 'League of Legends', currentRank: 'Master · 184 LP', peakRank: 'Grandmaster · 421 LP', lastGame: '6h ago', lastUpdated: '12 min ago', followed: true, initials: 'LU'},
  {id: 'follow-nori', riotId: 'nori#000', region: 'AP', games: ['VALORANT'], game: 'VALORANT', currentRank: 'Ascendant 1 · 33 RR', peakRank: 'Immortal 1', lastGame: '3d ago', lastUpdated: '1h ago', followed: true, initials: 'NO'},
]

const webFirstRunPreview = typeof window !== 'undefined'
  && new URLSearchParams(window.location?.search ?? '').get('firstRun') === '1'
const webPostMatchPreview = typeof window !== 'undefined'
  && new URLSearchParams(window.location?.search ?? '').get('postMatch') === '1'
let webPendingPin: string | null = null
let webPin = '2580'

let webState: AppState = {
  locked: true,
  hasPasscode: !webFirstRunPreview,
  pinMode: webFirstRunPreview ? 'create' : 'unlock',
  pinError: '',
  accounts,
  followed,
  searchHistory: ['quietly#EUW', 'lumen#soft'],
  currentMatch: {
    game: 'VALORANT',
    mode: 'Competitive',
    map: 'Abyss',
    elapsed: '18:42',
    status: 'Demo live session · sample stats',
    streamerMode: false,
    teams: valorantMatchTeams.map((team, teamIndex) => ({
      ...team,
      score: undefined,
      won: undefined,
      players: team.players.map((player, index) => ({...player, score: undefined, stats: livePreviewStats[teamIndex][index]})),
    })),
  },
  gameDetected: true,
  settings: {
    autoLockMinutes: 15,
    streamerMode: false,
    lockOnBlur: true,
    reduceMotion: false,
    riotApiConfigured: false,
    clipboardClearSeconds: 15,
  },
  riotClient: {detected: true, label: 'VALORANT · Competitive', game: 'VALORANT'},
}

const clone = <T,>(value: T): T => structuredClone(value)

// Development-only browser fixtures for visual checks across roster formats.
// Native invokes always bypass webState; these samples never reach Discord.
if (import.meta.env.DEV && typeof window !== 'undefined' && !window.peaks) {
  const accountCount = Number(new URLSearchParams(window.location?.search ?? '').get('accounts'))
  if (accountCount > 0 && accountCount <= 30) {
    webState.accounts = Array.from({length: Math.floor(accountCount)}, (_, index) => {
      const source = accounts[index % accounts.length]
      return {...source, id: `preview-account-${index}`, riotId: index < accounts.length ? source.riotId : `Player ${index + 1}#DEMO`}
    })
  }
  const layout = new URLSearchParams(window.location?.search ?? '').get('matchLayout')
  if (layout && ['deathmatch', 'retake', 'gauntlet', 'asymmetric'].includes(layout)) {
    const source = webState.currentMatch.teams?.flatMap(team => team.players) ?? []
    const count = layout === 'deathmatch' ? 14 : layout === 'gauntlet' ? 16 : layout === 'retake' ? 6 : 7
    const players = Array.from({length: count}, (_, index) => ({
      ...source[index % source.length],
      name: `Practice ${index + 1}#DEMO`, riotId: `Practice ${index + 1}#DEMO`,
      self: index === 0, hidden: false, partyId: undefined,
    }))
    webState.currentMatch = {
      ...webState.currentMatch,
      id: `preview-layout-${layout}`,
      mode: layout === 'deathmatch' ? 'Deathmatch' : layout === 'gauntlet' ? 'Gauntlet: Glitched' : layout === 'retake' ? 'Retake' : 'Skirmish',
      freeForAll: layout === 'deathmatch',
      status: 'Demo layout · synthetic roster and stats',
      teams: layout === 'deathmatch' ? [{name: 'Free for all', players}]
        : layout === 'gauntlet' ? Array.from({length: 8}, (_, index) => ({name: `Team ${index + 1}`, players: players.slice(index * 2, index * 2 + 2)}))
        : [{name: 'Your team', players: players.slice(0, 3)}, {name: 'Opponents', players: players.slice(3)}],
    }
  }
  if (layout === 'tft' || layout === 'tft-double-up') {
    const duos = layout === 'tft-double-up'
    const snapshotTime = Date.now() / 1000 - 24
    const players: MatchPlayer[] = Array.from({length: 8}, (_, index) => ({
      name: `Tactician ${index + 1}#DEMO`, riotId: `Tactician ${index + 1}#DEMO`,
      self: index === 2, currentRank: 'Gold III', peakRank: 'Platinum II',
      accountLevel: 80 + index * 14,
      stats: {
        health: [93, 87, 73, 64, 51, 26, 11, 0][index], standing: index + 1,
        boardUnits: [8, 8, 7, 7, 6, 6, 5, 5][index], observedAt: snapshotTime,
        ...(index === 1 ? {augmentCount: 2, level: 8} : {}),
      },
    }))
    webState.currentMatch = {
      id: `preview-layout-${layout}`, phase: 'live', game: 'Teamfight Tactics',
      queue: duos ? '1160' : '1100', mode: duos ? 'Double Up' : 'Ranked', map: 'Teamfight Tactics',
      status: 'Demo live session · synthetic TFT snapshot', elapsed: '23:17',
      freeForAll: !duos, ...(duos ? {teamMode: 'duos' as const} : {}),
      teams: duos ? Array.from({length: 4}, (_, index) => ({name: `Duo ${index + 1}`, grouping: 'duo' as const, players: players.slice(index * 2, index * 2 + 2)})) : [{name: 'Players', players}],
    }
    webState.riotClient = {detected: true, label: 'TFT · Demo snapshot', game: 'Teamfight Tactics'}
  }
}

let webTotpConfirmation: TotpSetupProposal | null = null
// This configuration exists only in this browser tab. Demo activity is never sent to Discord.
let webDiscordPresence = {enabled: true, applicationId: '1549634813756178503'}

// Browser-only fixture: exercise the real live-to-recorded transition during
// visual QA. Native desktop invokes always bypass webInvoke and this fixture.
if (webPostMatchPreview) {
  webState.currentMatch = {
    ...webState.currentMatch,
    id: `preview-post-match-${Date.now()}`,
    accountId: accounts[0].id,
    phase: 'live',
  }
}

const webInvoke = async <T,>(command: string, payload: Record<string, unknown> = {}): Promise<T> => {
  if (command === 'activity' && webPostMatchPreview && !webState.locked && webState.currentMatch.id) {
    const completed = {...accounts[0].matches![0], id: webState.currentMatch.id, playedAt: 'just now'}
    webState = {
      ...webState,
      accounts: webState.accounts.map(account => account.id === accounts[0].id
        ? {...account, matches: [completed, ...(account.matches ?? [])]}
        : account),
      currentMatch: {},
      gameDetected: false,
      riotClient: {detected: true, label: 'VALORANT · In menus', game: 'VALORANT'},
    }
  }
  if (command === 'state' || command === 'activity' || command === 'refresh') return clone(webState) as T

  if (command === 'pin') {
    const pin = String(payload.pin ?? '')
    if (!webState.hasPasscode && webState.pinMode === 'create') {
      webPendingPin = pin
      webState = {...webState, pinMode: 'confirm', pinError: ''}
      return clone(webState) as T
    }
    if (!webState.hasPasscode && webState.pinMode === 'confirm') {
      if (!webPendingPin || pin !== webPendingPin) throw new Error('Passcodes did not match')
      webPin = pin
      webPendingPin = null
      webState = {...webState, locked: false, hasPasscode: true, pinMode: 'unlock', pinError: ''}
      return clone(webState) as T
    }
    if (pin !== webPin) throw new Error('That passcode was not recognized')
    webState = {...webState, locked: false}
    return clone(webState) as T
  }

  if (command === 'reset_application') {
    if (!webState.locked || !webState.hasPasscode) {
      throw new Error('Lock Peaks before clearing its local data')
    }
    if (payload.confirmation !== RESET_APPLICATION_CONFIRMATION) {
      throw new Error('Confirm the local data reset before continuing')
    }
    webPendingPin = null
    webTotpConfirmation = null
    webState = {
      ...webState,
      locked: true,
      hasPasscode: false,
      pinMode: 'create',
      pinError: '',
      accounts: [],
      followed: [],
      searchHistory: [],
      currentMatch: {},
      gameDetected: false,
      settings: {
        autoLockMinutes: 15,
        streamerMode: false,
        lockOnBlur: true,
        reduceMotion: false,
        riotApiConfigured: false,
        clipboardClearSeconds: 15,
      },
      riotClient: {detected: false, label: 'Not detected', game: ''},
    }
    return clone(webState) as T
  }

  if (webState.locked) throw new Error('Unlock Peaks to continue')

  if (command === 'telemetry_settings') return {enabled: false, available: false} as T

  if (command === 'discord_presence') {
    if (!payload || typeof payload !== 'object' || Array.isArray(payload)
      || Object.keys(payload).some(key => key !== 'enabled' && key !== 'applicationId')) {
      throw new Error('Invalid Discord preferences')
    }
    const {enabled, applicationId} = payload
    if (enabled !== undefined && typeof enabled !== 'boolean') throw new Error('Choose whether Discord presence is enabled')
    if (applicationId !== undefined && (typeof applicationId !== 'string'
      || (applicationId.trim() !== '' && !/^[0-9]{17,20}$/.test(applicationId.trim())))) {
      throw new Error('Enter a public Discord Application ID containing 17–20 digits')
    }
    webDiscordPresence = {
      enabled: typeof enabled === 'boolean' ? enabled : webDiscordPresence.enabled,
      applicationId: typeof applicationId === 'string' ? applicationId.trim() : webDiscordPresence.applicationId,
    }
    return {
      ...webDiscordPresence,
      status: 'preview',
      detail: 'Browser preview only. Open Peaks on desktop to connect to Discord. Demo activity is never published.',
    } as T
  }

  if (command === 'change_pin') {
    const {oldPin, newPin, confirmPin} = payload
    if ([oldPin, newPin, confirmPin].some(value => typeof value !== 'string' || !/^[0-9]{4}$/.test(value))) {
      throw new Error('Enter four digits in each passcode field')
    }
    if (newPin !== confirmPin) throw new Error('The new passcodes do not match')
    if (oldPin !== webPin) throw new Error('The current passcode was not recognized')
    if (newPin === oldPin) throw new Error('Choose a different passcode')
    webPin = String(newPin)
  }
  if (command === 'lock') webState = {...webState, locked: true}
  if (command === 'settings') webState = {...webState, settings: {...webState.settings, ...payload}}
  if (command === 'api_key') {
    if (!String(payload.key ?? '').trim()) throw new Error('Enter an API key')
    webState = {...webState, settings: {...webState.settings, riotApiConfigured: true}}
  }
  if (command === 'add_account') {
    const accountNumber = webState.accounts.length + 1
    webState = {...webState, accounts: [...webState.accounts, {
      id: `web-${Date.now()}`,
      riotId: `Connected Player ${accountNumber}#EUW`,
      region: 'EUW',
      ranks: [],
      matches: [],
      hasTotp: false,
      connected: true,
      owned: true,
      lastUpdated: 'just now',
    }]}
  }
  if (command === 'remove_account') {
    const accountId = String(payload.accountId ?? '')
    if (!webState.accounts.some(account => account.id === accountId)) {
      throw new Error('That account is no longer available')
    }
    webState = {
      ...webState,
      accounts: webState.accounts.filter(account => account.id !== accountId),
    }
  }
  if (command === 'import_session') {
    const accountId = String(payload.accountId ?? '')
    webState = {
      ...webState,
      accounts: webState.accounts.map(account => account.id === accountId
        ? {...account, connected: true, lastUpdated: 'Demo Riot session'}
        : account),
    }
  }
  if (command === 'set_account_icon') {
    const accountId = String(payload.accountId ?? '')
    const icon = payload.icon as AccountIconSelection | null
    const preferences = 'nickname' in payload ? {nickname: String(payload.nickname ?? '').trim() || undefined} : {}
    webState = {...webState, accounts: webState.accounts.map(account => account.id === accountId
      ? {...account, ...preferences, accountIcon: icon ?? undefined} : account)}
  }
  if (command === 'connect_riot_client') {
    // Browser-only approval simulation; native commands always bypass this adapter.
    await new Promise(resolve => setTimeout(resolve, 2200))
    if (import.meta.env.DEV && new URLSearchParams(window.location?.search ?? '').get('accountConnect') === 'error') {
      throw new Error('No readable Riot sign-in QR was found.')
    }
    webState = {...webState, accounts: webState.accounts.map(account => account.id === payload.accountId
      ? {...account, connected: true} : account)}
  }
  if (command === 'connect_riot_qr_image') {
    const accountId = String(payload.accountId ?? '')
    webState = {
      ...webState,
      accounts: webState.accounts.map(account => account.id === accountId
        ? {...account, connected: true, lastUpdated: 'Pasted Riot QR'}
        : account),
    }
    return {
      ...clone(webState),
      operationNotice: 'Pasted Riot QR connected to the selected identity',
    } as T
  }
  if (command === 'toggle_watchlist' || command === 'toggle_follow') {
    const player = payload.player as Player | undefined
    if (player) {
      const exists = webState.followed.some(item => samePlayerIdentity(item, player))
      webState = {...webState, followed: exists
        ? webState.followed.filter(item => !samePlayerIdentity(item, player))
        : [...webState.followed, {...player, followed: true}]}
      return {
        ...clone(webState),
        operationNotice: exists ? 'Removed from Watchlist' : 'Added to Watchlist',
      } as T
    }
  }
  if (command === 'copy_totp') {
    await navigator.clipboard?.writeText('482106').catch(() => undefined)
  }
  if (command === 'enable_riot_mfa') {
    if (webState.locked) throw new Error('Unlock Peaks before enabling MFA')
    const accountId = String(payload.accountId ?? '')
    // Native requests bypass this synthetic browser-only state entirely.
    await new Promise(resolve => setTimeout(resolve, 450))
    const account = webState.accounts.find(item => item.id === accountId)
    if (!account || account.owned === false) throw new Error('Choose an owned account for MFA')
    if (account.hasTotp) throw new Error('An authenticator secret is already saved for this account')
    if (!(account.canConnectQr ?? account.connected)) throw new Error('Save a reusable Riot session for this account before setting up Riot MFA')
    webState = {
      ...webState,
      accounts: webState.accounts.map(item => item.id === accountId
        ? {...item, hasTotp: true, canSetupMfa: false}
        : item),
    }
    return clone<TotpSetupResult>({state: webState, seedSaved: true, verified: true, warning: null}) as T
  }
  if (command === 'prepare_totp_setup') {
    const accountId = String(payload.accountId ?? '')
    const account = webState.accounts.find(item => item.id === accountId)
    if (!account) throw new Error('Choose an account for authenticator setup')
    if (account.hasTotp) throw new Error('An authenticator secret is already saved for this account')
    webTotpConfirmation = {
      confirmationId: `web-totp-${accountId}`,
      accountId,
      riotId: account.riotId,
      expiresInSeconds: 300,
    }
    return clone(webTotpConfirmation) as T
  }
  if (command === 'confirm_totp_setup') {
    const accountId = String(payload.accountId ?? '')
    const confirmationId = String(payload.confirmationId ?? '')
    if (!webTotpConfirmation
      || webTotpConfirmation.accountId !== accountId
      || webTotpConfirmation.confirmationId !== confirmationId) {
      throw new Error('Authenticator setup confirmation expired; start again')
    }
    webTotpConfirmation = null
    webState = {
      ...webState,
      accounts: webState.accounts.map(account => account.id === accountId
        ? {...account, hasTotp: true}
        : account),
    }
    return clone<TotpSetupResult>({
      state: webState,
      seedSaved: true,
      verified: true,
      warning: null,
    }) as T
  }
  if (command === 'cancel_totp_setup') {
    if (webTotpConfirmation?.confirmationId === String(payload.confirmationId ?? '')) {
      webTotpConfirmation = null
    }
  }
  if (command === 'search') {
    const query = String(payload.query ?? '').trim() || 'summoner#tag'
    const game = payload.game ? String(payload.game) as Game : undefined
    const player: Player = {
      id: `search-${query.toLowerCase()}`,
      riotId: query,
      region: String(payload.region ?? 'EUW'),
      game,
      games: game ? [game] : ['League of Legends', 'Teamfight Tactics'],
      ranks: game ? undefined : [
        {game: 'League of Legends', tier: 'Diamond IV', rating: 62},
        {game: 'Teamfight Tactics', tier: 'Gold III', rating: 68},
      ],
      currentRank: game === 'VALORANT' ? 'Ascendant 1 · 48 RR' : 'Diamond IV · 62 LP',
      peakRank: game === 'VALORANT' ? 'Immortal 1' : 'Master',
      lastUpdated: 'Demo data',
      followed: false,
    }
    webState = {...webState, searchHistory: [query, ...webState.searchHistory.filter(item => item.toLowerCase() !== query.toLowerCase())]}
    return [player] as T
  }

  return clone(webState) as T
}

export const invoke = <T,>(command: string, payload?: unknown): Promise<T> => {
  if (window.peaks) return window.peaks.invoke<T>(command, payload)
  return webInvoke<T>(command, (payload ?? {}) as Record<string, unknown>)
}
