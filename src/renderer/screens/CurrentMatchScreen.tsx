import {t, useLocale, displayText} from '../i18n'
import {EmptyState} from '@astryxdesign/core/EmptyState'
import {Heading} from '@astryxdesign/core/Heading'
import {HStack} from '@astryxdesign/core/HStack'
import {Icon} from '@astryxdesign/core/Icon'
import {Section} from '@astryxdesign/core/Section'
import {StatusDot} from '@astryxdesign/core/StatusDot'
import {Text} from '@astryxdesign/core/Text'
import {VStack} from '@astryxdesign/core/VStack'
import {Clock3, Radio, UsersRound} from 'lucide-react'
import {valorantMapName} from '../assets'
import {fitsValorantRoster} from '../matchLayout'
import {PlayerMatchCards} from '../components/PlayerMatchCards'
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
    return <AuthenticatedScreen eyebrow={t("LIVE SESSION")} screen="current-match" title={t("Current match")}>
      <VStack className="pd-detail pd-live" gap={6}>
        <Section className="pd-live__standby pd-riot-surface" padding={8} variant="transparent">
          <VStack className="pd-detail__art-content" gap={8} justify="between">
            <HStack align="center" gap={2}><StatusDot label={t("Waiting for a session")} variant="neutral" /><Text className="pd-detail__eyebrow" type="supporting">{t("WAITING FOR A SESSION")}</Text></HStack>
            <VStack className="pd-live__standby-copy" gap={4}><Heading className="pd-detail__display" level={2} type="display-1">{t("No active session")}</Heading><Text color="secondary">{t("Join a lobby or start a game in VALORANT, League of Legends, or Teamfight Tactics.")}</Text></VStack>
          </VStack>
        </Section>
      </VStack>
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
  const hasScore = isLive && !match.freeForAll && teams.length === 2 && teams.every(team => team.score != null && /^\d+$/.test(String(team.score)))
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
  return <AuthenticatedScreen
    fitContent={fitRoster}
    actions={<HStack align="center" gap={4}>
      {fitRoster ? score : null}
      {fitRoster && match.elapsed ? <Text hasTabularNumbers>{match.elapsed}</Text> : null}
      <HStack align="center" gap={2}><StatusDot isPulsing={!match.isStale && (phase === 'matchmaking' || phase === 'readycheck' || isLive)} label={status} variant={phase === 'readycheck' && !match.isStale ? 'success' : 'neutral'} /><Text weight="semibold">{status.toUpperCase()}</Text></HStack>
    </HStack>}
    description={[match.game ?? 'Riot', mode, label].filter(Boolean).join(' · ')}
    eyebrow={t("LIVE SESSION")} screen="current-match" title={fitRoster ? title : t("Current match")}>
    <VStack className="pd-detail pmc-match-screen" gap={fitRoster ? 2 : 5} height={fitRoster ? '100%' : undefined}>
      {!fitRoster ? <Section className="pmc-match-banner pd-riot-surface" padding={5} variant="transparent">
        <HStack align="center" justify="between" gap={5} wrap="wrap">
          <VStack gap={1}><Text className="pd-detail__eyebrow" type="supporting">{[match.game ?? 'RIOT GAMES', mode].filter(Boolean).join(' · ')}</Text><Heading className="pmc-match-banner__title" level={2}>{title}</Heading></VStack>
          {score ?? <Text color="secondary">{match.isStale ? t("Waiting for the client to reconnect.") : t(phaseDescription[phase])}</Text>}
          {match.elapsed && phase !== 'lobby' ? <HStack align="center" gap={2}><Icon icon={Clock3} color="secondary" /><Text hasTabularNumbers>{match.elapsed}</Text></HStack> : null}
        </HStack>
      </Section> : null}

      <HStack className="pmc-match-toolbar" align="center" justify="between" gap={4} wrap="wrap">
        <HStack align="center" gap={2}><Icon icon={UsersRound} color="secondary" /><Text type="supporting">{rosterLabel}</Text></HStack>
      </HStack>

      {playerCount > 0 ? <PlayerMatchCards fitToHeight={fitRoster} teams={teams} game={match.game} phase={phase} mode={match.mode} queueId={match.queue} modeId={match.modeId} map={match.map} matchId={match.id} result={isLive ? 'Live' : undefined} label={label} freeForAll={match.freeForAll} teamMode={match.teamMode} allowReorder={!match.isStale} onSelectPlayer={onSelectPlayer} /> : <EmptyState description={isParty ? t("Party members will appear when your lobby is available.") : t("Player details will appear when your game shares the roster.")} icon={<Icon color="secondary" icon={Radio} />} title={isParty ? t("Waiting for your party") : t("Waiting for players")} />}
    </VStack>
  </AuthenticatedScreen>
}
