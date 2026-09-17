import {EmptyState} from '@astryxdesign/core/EmptyState'
import {Heading} from '@astryxdesign/core/Heading'
import {HStack} from '@astryxdesign/core/HStack'
import {Icon} from '@astryxdesign/core/Icon'
import {Section} from '@astryxdesign/core/Section'
import {StatusDot} from '@astryxdesign/core/StatusDot'
import {Text} from '@astryxdesign/core/Text'
import {Token} from '@astryxdesign/core/Token'
import {VStack} from '@astryxdesign/core/VStack'
import {Clock3, Radio, UsersRound} from 'lucide-react'
import {gameArtwork, valorantMapName} from '../assets'
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
  const match = state.currentMatch
  if (!state.gameDetected) {
    return <AuthenticatedScreen eyebrow="LIVE SESSION" screen="current-match" title="Current match">
      <VStack className="pd-detail pd-live" gap={6}>
        <Section className="pd-live__standby pd-detail__art" padding={8} variant="transparent" style={{backgroundImage: `url("${gameArtwork('VALORANT')}")`}}>
          <VStack className="pd-detail__art-content" gap={8} justify="between">
            <HStack align="center" gap={2}><StatusDot label="Waiting for a session" variant="neutral" /><Text className="pd-detail__eyebrow" type="supporting">WAITING FOR A SESSION</Text></HStack>
            <VStack className="pd-live__standby-copy" gap={4}><Heading className="pd-detail__display" level={2} type="display-1">No active session</Heading><Text color="secondary">Join a lobby or start a game in VALORANT, League of Legends, or Teamfight Tactics.</Text></VStack>
          </VStack>
        </Section>
      </VStack>
    </AuthenticatedScreen>
  }

  const teams = match.teams ?? []
  const phase = match.phase ?? 'live'
  const label = phaseLabel(phase, match.game)
  const isParty = ['lobby', 'matchmaking', 'readycheck'].includes(phase)
  const isLive = phase === 'live'
  const sourceMode = match.mode || match.queue
  const mode = sourceMode && !sourceMode.startsWith('/') && !/^\d+$/.test(sourceMode)
    ? modeLabels[sourceMode.toLowerCase()] ?? titleCase(sourceMode)
    : undefined
  const map = match.map && !/^(unknown map|unknown|current match)$/i.test(match.map)
    ? match.game === 'VALORANT' ? valorantMapName(match.map) : match.map
    : undefined
  const title = isParty ? phase === 'lobby' ? 'Your lobby' : label : map || label
  const hasScore = isLive && !match.freeForAll && teams.length === 2 && teams.every(team => team.score != null && /^\d+$/.test(String(team.score)))
  const playerCount = teams.reduce((total, team) => total + team.players.length, 0)
  const partyCount = match.partySize ?? playerCount
  const rosterLabel = isParty
    ? `${partyCount}${match.partyMax ? ` / ${match.partyMax}` : ''} ${partyCount === 1 ? 'player' : 'players'} in your party`
    : `${playerCount} ${playerCount === 1 ? 'player' : 'players'} in this session`
  const status = match.isStale ? 'Awaiting update' : label
  return <AuthenticatedScreen
    actions={<HStack align="center" gap={2}><StatusDot isPulsing={!match.isStale && (phase === 'matchmaking' || phase === 'readycheck' || isLive)} label={status} variant={phase === 'readycheck' && !match.isStale ? 'success' : 'neutral'} /><Text weight="semibold">{status.toUpperCase()}</Text></HStack>}
    description={[match.game ?? 'Riot', mode, label].filter(Boolean).join(' · ')}
    eyebrow="LIVE SESSION" screen="current-match" title="Current match">
    <VStack className="pd-detail pmc-match-screen" gap={5}>
      <Section className="pmc-match-banner" padding={5} variant="transparent" style={{backgroundImage: `url("${gameArtwork(match.game, match.map)}")`}}>
        <HStack align="center" justify="between" gap={5} wrap="wrap">
          <VStack gap={1}><Text className="pd-detail__eyebrow" type="supporting">{[match.game ?? 'RIOT GAMES', mode].filter(Boolean).join(' · ')}</Text><Heading className="pmc-match-banner__title" level={2}>{title}</Heading></VStack>
          {hasScore ? <Text className="pmc-match-banner__score" hasTabularNumbers weight="bold">{teams[0].score} : {teams[1].score}</Text> : <Text color="secondary">{match.isStale ? 'Waiting for the client to reconnect.' : phaseDescription[phase]}</Text>}
          {match.elapsed && phase !== 'lobby' ? <HStack align="center" gap={2}><Icon icon={Clock3} color="secondary" /><Text hasTabularNumbers>{match.elapsed}</Text></HStack> : null}
        </HStack>
      </Section>

      <HStack className="pmc-match-toolbar" align="center" justify="between" gap={4} wrap="wrap">
        <HStack align="center" gap={2}><Icon icon={UsersRound} color="secondary" /><Text type="supporting">{rosterLabel}</Text></HStack>
        <HStack className="pmc-legend" align="center" gap={2}><Token className="pmc-tag pmc-tag--past" label="Past games" size="sm" />{isLive ? <Token className="pmc-tag pmc-tag--match" label="This match" size="sm" /> : null}</HStack>
      </HStack>

      {playerCount > 0 ? <PlayerMatchCards teams={teams} game={match.game} phase={phase} mode={match.mode} queueId={match.queue} modeId={match.modeId} map={match.map} matchId={match.id} result={isLive ? 'Live' : undefined} label={label} freeForAll={match.freeForAll} teamMode={match.teamMode} allowReorder={!match.isStale} onSelectPlayer={onSelectPlayer} /> : <EmptyState description={isParty ? 'Party members will appear when your lobby is available.' : 'Player details will appear when your game shares the roster.'} icon={<Icon color="secondary" icon={Radio} />} title={isParty ? 'Waiting for your party' : 'Waiting for players'} />}
    </VStack>
  </AuthenticatedScreen>
}
