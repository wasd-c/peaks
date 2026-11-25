import {Alert, Badge, Flex, Result, Tag, Tooltip, Typography} from 'antd'
import {Radar} from 'lucide-react'
import {gameProfileIcon} from '../profileAssets'
import {PROFILE_GAMES} from '../riotProfile'
import {t, useLocale, displayText} from '../i18n'
import {EmptyState, Icon, Text, VStack} from '../ui'
import {Clock3, Radio, UsersRound} from 'lucide-react'
import {valorantMapName} from '../assets'
import {fitsValorantRoster, resolveMatchLayout} from '../matchLayout'
import {PlayerMatchCards} from '../components/PlayerMatchCards'
import {TftLiveStandings} from '../components/TftLiveStandings'
import {ValorantLiveScoreboard} from '../components/ValorantLiveScoreboard'
import {LiveMatchHeader} from '../components/LiveMatchHeader'
import type {AppState, Game, Player, SessionPhase} from '../types'
import {AuthenticatedScreen, titleCase} from './shared'

const modeLabels: Record<string, string> = {
  competitive: 'Competitive', unrated: 'Unrated', swiftplay: 'Swiftplay',
  spikerush: 'Spike Rush', deathmatch: 'Deathmatch', hurm: 'Team Deathmatch',
  escalation: 'Escalation', gungame: 'Escalation', onefa: 'Replication',
  retake: 'Retake', skirmish: 'Skirmish', premier: 'Premier', custom: 'Custom',
  classic: 'Summoner’s Rift', aram: 'ARAM', ranked_solo_5x5: 'Ranked Solo / Duo',
  ranked_flex_sr: 'Ranked Flex', ranked_tft: 'Ranked', tft: 'Normal',
  ranked_tft_double_up: 'Double Up', ranked_tft_turbo: 'Hyper Roll',
}

function phaseLabel(phase: SessionPhase, game?: Game) {
  if (phase === 'lobby') return 'Lobby'
  if (phase === 'matchmaking') return 'In queue'
  if (phase === 'readycheck') return 'Match found'
  if (phase === 'pregame') return game === 'VALORANT' ? 'Agent select' : game === 'Teamfight Tactics' ? 'Getting ready' : 'Champion select'
  return 'In game'
}

const phaseDescription: Record<SessionPhase, string> = {
  lobby: 'Your party is getting ready.',
  matchmaking: 'Searching for a match.',
  readycheck: 'Accept the match in your game client.',
  pregame: 'The match is getting ready.',
  live: 'Match in progress',
}

export interface CurrentMatchScreenProps {
  state: AppState
  onSelectPlayer: (player: Player) => void
}

export function CurrentMatchScreen({state, onSelectPlayer}: CurrentMatchScreenProps) {
  useLocale()
  const match = state.currentMatch
  if (!state.gameDetected) {
    return <AuthenticatedScreen screen="current-match" title={t("Current match")}>
      <Result className="pd-live-standby" icon={<Radar size={56} aria-hidden className="pd-live-standby__icon" />} title={t("No active session")}
        extra={<Flex gap={20} justify="center" aria-label={t("Join a lobby or start a game in VALORANT, League of Legends, or Teamfight Tactics.")} role="img">
          {PROFILE_GAMES.map(game => <Tooltip key={game} title={game}><img className="pd-riot-game-icon pd-riot-game-icon--standby" src={gameProfileIcon(game)} alt="" /></Tooltip>)}
        </Flex>} />
    </AuthenticatedScreen>
  }

  const teams = match.teams ?? []
  const phase = match.phase ?? 'live'
  const label = t(phaseLabel(phase, match.game))
  const isParty = ['lobby', 'matchmaking', 'readycheck'].includes(phase)
  const isLive = phase === 'live'
  const sourceMode = match.mode || match.queue
  const mode = sourceMode && !sourceMode.startsWith('/') && !/^\d+$/.test(sourceMode)
    ? displayText(modeLabels[sourceMode.toLowerCase()] ?? titleCase(sourceMode))
    : undefined
  const map = match.map && !/^(unknown map|unknown|current match)$/i.test(match.map)
    ? match.game === 'VALORANT' ? valorantMapName(match.map) : match.map
    : undefined
  const title = isParty ? phase === 'lobby' ? t('Your lobby') : label : map || label
  const hasScore = isLive && match.game !== 'Teamfight Tactics' && teams.length === 2
    && teams.every(team => team.score != null && /^\d+$/.test(String(team.score)))
    && resolveMatchLayout({...match, teams, queueId: match.queue}).kind === 'teams'
  const playerCount = teams.reduce((total, team) => total + team.players.length, 0)
  const partyCount = match.partySize ?? playerCount
  const rosterLabel = isParty
    ? t('{{count}}{{capacity}} players in your party', {count: partyCount, capacity: match.partyMax ? ` / ${match.partyMax}` : ''})
    : t('{{count}} players in this session', {count: playerCount})
  const status = match.isStale ? t('Awaiting update') : label
  const fitRoster = fitsValorantRoster({...match, teams, queueId: match.queue})
  // Match the roster's order: your team first, regardless of the provider's order.
  const scoreTeams = [...teams].sort((left, right) => Number(right.players.some(player => player.self)) - Number(left.players.some(player => player.self)))
  const ownTeam = scoreTeams.find(team => team.players.some(player => player.self))
  const score = hasScore ? <Text className="pmc-match-banner__score" hasTabularNumbers weight="bold">
    <Text type="inherit" className={`pmc-score--${ownTeam ? 'ally' : 'neutral'}`}>{scoreTeams[0].score}</Text>
    <Text type="inherit" color="secondary">{' : '}</Text>
    <Text type="inherit" className={`pmc-score--${ownTeam ? 'enemy' : 'neutral'}`}>{scoreTeams[1].score}</Text>
  </Text> : null
  const pulsing = !match.isStale && (phase === 'matchmaking' || phase === 'readycheck' || isLive)
  if (isLive && playerCount > 0 && (match.game === 'VALORANT' || match.game === 'Teamfight Tactics')) {
    const liveTitle = (map && map !== match.game ? map : mode) || match.game
    return <AuthenticatedScreen screen="current-match" title={liveTitle}
      heading={<LiveMatchHeader game={match.game} title={liveTitle} mode={mode} elapsed={match.elapsed} players={teams.flatMap(team => team.players)} score={score} stale={match.isStale} />}>
      {match.game === 'VALORANT'
        ? <ValorantLiveScoreboard key={match.id} match={match} onSelectPlayer={onSelectPlayer} />
        : <TftLiveStandings key={match.id} match={match} onSelectPlayer={onSelectPlayer} />}
    </AuthenticatedScreen>
  }
  return <AuthenticatedScreen
    fitContent={fitRoster}
    title={title}
    heading={<Flex gap={12} align="center" wrap className="pd-live-heading">
      {match.game ? <img className="pd-riot-game-icon pd-riot-game-icon--heading" src={gameProfileIcon(match.game)} alt={match.game} /> : null}
      <Typography.Title level={3} className="peaks-screen__title">{title}</Typography.Title>
      {mode && mode !== title ? <Tag className="pd-live-mode">{mode}</Tag> : null}
    </Flex>}
    actions={<>
      {score}
      {match.elapsed && phase !== 'lobby' ? <Tooltip title={t('Elapsed time')}><Typography.Text className="pd-live-stat"><Clock3 size={14} aria-hidden /> {match.elapsed}</Typography.Text></Tooltip> : null}
      {playerCount > 0 ? <Tooltip title={rosterLabel}><Typography.Text className="pd-live-stat" aria-label={rosterLabel}><UsersRound size={14} aria-hidden /> {isParty && match.partyMax ? `${partyCount}/${match.partyMax}` : playerCount}</Typography.Text></Tooltip> : null}
      <Tooltip title={match.isStale ? t("Waiting for the client to reconnect.") : t(phaseDescription[phase])}>
        <Badge status={match.isStale ? 'default' : phase === 'readycheck' ? 'success' : pulsing ? 'processing' : 'default'} text={status} className="pd-live-status" />
      </Tooltip>
    </>}
    screen="current-match">
    <VStack className="pd-detail pmc-match-screen" gap={fitRoster ? 2 : 4} height={fitRoster ? '100%' : undefined}>
      {phase === 'readycheck' && !match.isStale ? <Alert type="success" showIcon title={t(phaseDescription[phase])} /> : null}
      {playerCount > 0 ? <PlayerMatchCards fitToHeight={fitRoster} teams={teams} game={match.game} phase={phase} mode={match.mode} queueId={match.queue} modeId={match.modeId} map={match.map} matchId={match.id} result={isLive ? 'Live' : undefined} label={label} freeForAll={match.freeForAll} teamMode={match.teamMode} allowReorder={!match.isStale} onSelectPlayer={onSelectPlayer} /> : <EmptyState description={isParty ? t("Party members will appear when your lobby is available.") : t("Player details will appear when your game shares the roster.")} icon={<Icon color="secondary" icon={Radio} />} title={isParty ? t("Waiting for your party") : t("Waiting for players")} />}
    </VStack>
  </AuthenticatedScreen>
}
