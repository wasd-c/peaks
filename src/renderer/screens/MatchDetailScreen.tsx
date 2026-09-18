import {t, useLocale, displayText} from '../i18n'
import {useState} from 'react'
import {Button} from '@astryxdesign/core/Button'
import {EmptyState} from '@astryxdesign/core/EmptyState'
import {Heading} from '@astryxdesign/core/Heading'
import {HStack} from '@astryxdesign/core/HStack'
import {Icon} from '@astryxdesign/core/Icon'
import {Section} from '@astryxdesign/core/Section'
import {Tab, TabList} from '@astryxdesign/core/TabList'
import {Text} from '@astryxdesign/core/Text'
import {Token} from '@astryxdesign/core/Token'
import {VStack} from '@astryxdesign/core/VStack'
import {ArrowLeft, BarChart3, Clock3, Share2, UsersRound} from 'lucide-react'
import {gameArtwork, valorantMapName} from '../assets'
import {ShareMatchDialog} from '../components/ShareMatchDialog'
import {MatchInsights} from '../components/MatchInsights'
import {PlayerMatchCards} from '../components/PlayerMatchCards'
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
  const map = match.game === 'VALORANT' ? valorantMapName(match.map) : match.map ?? 'Map unavailable'
  const teams = match.teams ?? []

  return <>
    <AuthenticatedScreen
      actions={<Button icon={<Icon icon={Share2} />} label={t("Share match")} onClick={() => setShareOpen(true)} />}
      description={`${displayText(titleCase(match.mode ?? 'Match'))} · ${displayText(match.playedAt ?? 'Time unavailable')}`}
      eyebrow={t("MATCH REPORT")}
      screen="match-detail"
      title={t("Match report")}>
      <VStack className="pd-detail pmc-match-screen" gap={5}>
        <HStack align="center" justify="between" gap={3} wrap="wrap">
          <Button icon={<Icon icon={ArrowLeft} />} label={t("Match history")} onClick={onBack} size="sm" variant="ghost" />
        </HStack>

        <Section className="pmc-match-banner" padding={5} variant="transparent" style={{backgroundImage: `url("${gameArtwork(match.game, match.map)}")`}}>
          <HStack align="center" justify="between" gap={5} wrap="wrap">
            <VStack gap={1}><Text className="pd-detail__eyebrow" type="supporting">{match.game} · {displayText(titleCase(match.mode ?? 'Match'))}</Text><Heading className="pmc-match-banner__title" level={2}>{displayText(map)}</Heading></VStack>
            <HStack align="center" gap={4}><Token color={resultColor(match.result)} label={displayText(match.result)} /><Text className="pmc-match-banner__score" hasTabularNumbers weight="bold">{match.score ?? '—'}</Text></HStack>
            <VStack align="end" gap={1}><HStack align="center" gap={2}><Icon icon={Clock3} color="secondary" /><Text hasTabularNumbers>{match.duration ?? t("Duration unavailable")}</Text></HStack><Text type="supporting">{displayText(match.playedAt ?? 'Recent match')}</Text></VStack>
          </HStack>
        </Section>

        <HStack className="pmc-match-toolbar" align="center" justify="between" gap={4}>
          <TabList className="pd-detail__tabs" aria-label={t("Match report views")} hasDivider onChange={setTab} role="tablist" value={activeTab}>
            <Tab icon={<Icon icon={UsersRound} />} label={t("Scoreboard")} panelId="match-scoreboard-panel" value="scoreboard" />
            {match.game === 'VALORANT' ? <Tab icon={<Icon icon={BarChart3} />} label={t("Performance")} panelId="match-performance-panel" value="performance" /> : null}
          </TabList>
          <HStack className="pmc-legend" align="center" gap={2} wrap="wrap"><Token className="pmc-tag pmc-tag--past" label={t("Past games")} size="sm" /><Token className="pmc-tag pmc-tag--match" label={t("This match")} size="sm" /></HStack>
        </HStack>

        {activeTab === 'performance' ? <Section className="pd-detail__panel" aria-label={t("Performance")} id="match-performance-panel" role="tabpanel" padding={0} variant="transparent"><MatchInsights match={match} /></Section> : <VStack className="pd-detail__panel" aria-label={t("Scoreboard")} gap={5} id="match-scoreboard-panel" role="tabpanel">
          {teams.length > 0 ? <PlayerMatchCards teams={teams} game={match.game} mode={match.mode} map={match.map} matchId={match.id} result={match.result} label={displayText(match.playedAt ?? 'Recent match')} freeForAll={match.freeForAll} teamMode={match.teamMode} region={region} completed onSelectPlayer={onSelectPlayer} /> : <EmptyState description={t("Refresh the account to try again.")} icon={<Icon color="secondary" icon={UsersRound} />} title={t("Players unavailable")} />}
          <Text color="secondary">{t("Select a Riot ID to open the player profile.")}</Text>
        </VStack>}
      </VStack>
    </AuthenticatedScreen>
    <ShareMatchDialog isOpen={isShareOpen} match={match} onOpenChange={setShareOpen} />
  </>
}
