import {t, useLocale, displayText} from '../i18n'
import {useState} from 'react'
import {Button, EmptyState, Heading, HStack, Icon, Section, Tab, TabList, Text, Token, VStack} from '../ui'
import {ArrowLeft, BarChart3, Clock3, Share2, UsersRound} from 'lucide-react'
import {gameArtwork, valorantMapName} from '../assets'
import {ShareMatchDialog} from '../components/ShareMatchDialog'
import {MatchInsights} from '../components/MatchInsights'
import {PlayerMatchCards} from '../components/PlayerMatchCards'
import {fitsValorantRoster} from '../matchLayout'
import {gameMode} from '../riotProfile'
import type {Match, Player} from '../types'
import {AuthenticatedScreen, resultColor, titleCase} from './shared'

export interface MatchDetailScreenProps {
  match: Match
  region?: string
  onBack: () => void
  onSelectPlayer: (player: Player) => void
}

export function MatchDetailScreen({match, region, onBack, onSelectPlayer}: MatchDetailScreenProps) {
  useLocale()
  const [isShareOpen, setShareOpen] = useState(false)
  const [tab, setTab] = useState('scoreboard')
  const activeTab = match.game === 'VALORANT' ? tab : 'scoreboard'
  const mode = match.game === 'VALORANT' ? titleCase(match.mode ?? 'Match') : gameMode(match)
  const map = match.game === 'VALORANT' ? valorantMapName(match.map) : match.map ?? (match.game === 'Teamfight Tactics' ? 'Teamfight Tactics' : 'Map unavailable')
  const seconds = match.durationSeconds
  const duration = match.duration ?? (typeof seconds === 'number' && Number.isFinite(seconds) && seconds > 0
    ? `${Math.floor(seconds / 60)}:${String(Math.floor(seconds % 60)).padStart(2, '0')}`
    : t('Duration unavailable'))
  const teams = match.teams ?? []
  const fitRoster = activeTab === 'scoreboard' && fitsValorantRoster({...match, teams})

  return <>
    <AuthenticatedScreen
      fitContent={fitRoster}
      actions={<HStack align="center" gap={3}>{fitRoster ? <><Token color={resultColor(match.result)} label={displayText(match.result)} /><Text hasTabularNumbers weight="bold">{match.score ?? '—'}</Text><Button icon={<Icon icon={ArrowLeft} />} label={t("Back")} onClick={onBack} size="sm" variant="ghost" /></> : null}<Button icon={<Icon icon={Share2} />} label={t("Share match")} onClick={() => setShareOpen(true)} /></HStack>}
      description={`${displayText(mode)} · ${displayText(match.playedAt ?? 'Time unavailable')}`}
      eyebrow={t("MATCH REPORT")}
      screen="match-detail"
      title={fitRoster ? displayText(map) : t("Match report")}>
      <VStack className="pd-detail pmc-match-screen" height={fitRoster ? '100%' : undefined} gap={fitRoster ? 2 : 5}>
        {!fitRoster ? <HStack align="center" justify="between" gap={3} wrap="wrap">
          <Button icon={<Icon icon={ArrowLeft} />} label={t("Back")} onClick={onBack} size="sm" variant="ghost" />
        </HStack> : null}

        {!fitRoster ? <Section className="pmc-match-banner" padding={5} variant="transparent" style={{backgroundImage: `url("${gameArtwork(match.game, match.map)}")`}}>
          <HStack align="center" justify="between" gap={5} wrap="wrap">
            <VStack gap={1}><Text className="pd-detail__eyebrow" type="supporting">{match.game} · {displayText(mode)}</Text><Heading className="pmc-match-banner__title" level={2}>{displayText(map)}</Heading></VStack>
            <HStack align="center" gap={4}><Token color={resultColor(match.result)} label={displayText(match.result)} /><Text className="pmc-match-banner__score" hasTabularNumbers weight="bold">{match.score ?? '—'}</Text></HStack>
            <VStack align="end" gap={1}><HStack align="center" gap={2}><Icon icon={Clock3} color="secondary" /><Text hasTabularNumbers>{duration}</Text></HStack><Text type="supporting">{displayText(match.playedAt ?? 'Recent match')}</Text></VStack>
          </HStack>
        </Section> : null}

        <HStack className="pmc-match-toolbar" align="center" justify="between" gap={4}>
          <TabList className="pd-detail__tabs" aria-label={t("Match report views")} hasDivider onChange={setTab} role="tablist" value={activeTab}>
            <Tab icon={<Icon icon={UsersRound} />} label={t("Scoreboard")} panelId="match-scoreboard-panel" value="scoreboard" />
            {match.game === 'VALORANT' ? <Tab icon={<Icon icon={BarChart3} />} label={t("Performance")} panelId="match-performance-panel" value="performance" /> : null}
          </TabList>
          <HStack className="pmc-legend" align="center" gap={2} wrap="wrap"><Token className="pmc-tag pmc-tag--past" label={t("Past games")} size="sm" /><Token className="pmc-tag pmc-tag--match" label={t("This match")} size="sm" /></HStack>
        </HStack>

        {activeTab === 'performance' ? <Section className="pd-detail__panel" aria-label={t("Performance")} id="match-performance-panel" role="tabpanel" padding={0} variant="transparent"><MatchInsights match={match} /></Section> : <VStack className="pd-detail__panel" aria-label={t("Scoreboard")} gap={5} id="match-scoreboard-panel" role="tabpanel">
          {teams.length > 0 ? <PlayerMatchCards teams={teams} game={match.game} mode={match.mode} map={match.map} matchId={match.id} result={match.result} label={displayText(match.playedAt ?? 'Recent match')} freeForAll={match.freeForAll} teamMode={match.teamMode} region={region} completed fitToHeight={fitRoster} onSelectPlayer={onSelectPlayer} /> : <EmptyState description={t("Refresh the account to try again.")} icon={<Icon color="secondary" icon={UsersRound} />} title={t("Players unavailable")} />}
        </VStack>}
      </VStack>
    </AuthenticatedScreen>
    <ShareMatchDialog isOpen={isShareOpen} match={match} onOpenChange={setShareOpen} />
  </>
}
