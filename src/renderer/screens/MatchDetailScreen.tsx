import {Button as AntButton, Flex, Segmented, Tag, Tooltip, Typography} from 'antd'
import {gameProfileIcon} from '../profileAssets'
import {t, useLocale, displayText} from '../i18n'
import {useState} from 'react'
import {EmptyState, Icon, VStack} from '../ui'
import {ArrowLeft, BarChart3, CalendarDays, Clock3, Share2, UsersRound} from 'lucide-react'
import {valorantMapName} from '../assets'
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

  const tagColor = {green: 'success', red: 'error', yellow: 'gold'}[resultColor(match.result) as string]
  return <>
    <AuthenticatedScreen
      fitContent={fitRoster}
      screen="match-detail"
      title={displayText(map)}
      heading={<Flex gap={12} align="center" wrap>
        <Tooltip title={t("Back")}><AntButton type="text" icon={<ArrowLeft size={18} />} aria-label={t("Back")} onClick={onBack} /></Tooltip>
        <img className="pd-riot-game-icon pd-riot-game-icon--heading" src={gameProfileIcon(match.game)} alt={match.game} />
        <Typography.Title level={3} className="peaks-screen__title">{displayText(map)}</Typography.Title>
        <Tag>{displayText(mode)}</Tag>
        <Tag color={tagColor}>{displayText(match.result)}</Tag>
      </Flex>}
      actions={<>
        {match.score ? <Typography.Text strong className="pmc-match-banner__score">{match.score}</Typography.Text> : null}
        <Tooltip title={t('Duration')}><Typography.Text className="pd-live-stat"><Clock3 size={14} aria-hidden /> {duration}</Typography.Text></Tooltip>
        {match.playedAt ? <Tooltip title={t('Played')}><Typography.Text className="pd-live-stat"><CalendarDays size={14} aria-hidden /> {displayText(match.playedAt)}</Typography.Text></Tooltip> : null}
        {match.game === 'VALORANT' ? <Segmented value={activeTab} onChange={value => setTab(value as typeof tab)} aria-label={t("Match report views")} options={[
          {value: 'scoreboard', icon: <UsersRound size={16} aria-hidden />, title: t("Scoreboard")},
          {value: 'performance', icon: <BarChart3 size={16} aria-hidden />, title: t("Performance")},
        ]} /> : null}
        <Tooltip title={t("Share match")}><AntButton icon={<Share2 size={16} />} aria-label={t("Share match")} onClick={() => setShareOpen(true)} /></Tooltip>
      </>}>
      <VStack className="pd-detail pmc-match-screen" height={fitRoster ? '100%' : undefined} gap={fitRoster ? 2 : 4}>
        {activeTab === 'performance' ? <section className="pd-detail__panel" aria-label={t("Performance")} id="match-performance-panel"><MatchInsights match={match} /></section> : <VStack className="pd-detail__panel" aria-label={t("Scoreboard")} gap={5} id="match-scoreboard-panel">
          {teams.length > 0 ? <PlayerMatchCards teams={teams} game={match.game} mode={match.mode} map={match.map} matchId={match.id} result={match.result} label={displayText(match.playedAt ?? 'Recent match')} freeForAll={match.freeForAll} teamMode={match.teamMode} region={region} completed fitToHeight={fitRoster} onSelectPlayer={onSelectPlayer} /> : <EmptyState description={t("Refresh the account to try again.")} icon={<Icon color="secondary" icon={UsersRound} />} title={t("Players unavailable")} />}
        </VStack>}
      </VStack>
    </AuthenticatedScreen>
    <ShareMatchDialog isOpen={isShareOpen} match={match} onOpenChange={setShareOpen} />
  </>
}
