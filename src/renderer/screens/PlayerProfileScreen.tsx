import {t, useLocale, displayText} from '../i18n'
import {usePlayerPrivacy} from '../components/PlayerPrivacy'
import {useState} from 'react'
import {Avatar} from '@astryxdesign/core/Avatar'
import {Button} from '@astryxdesign/core/Button'
import {EmptyState} from '@astryxdesign/core/EmptyState'
import {Grid} from '@astryxdesign/core/Grid'
import {Heading} from '@astryxdesign/core/Heading'
import {HStack} from '@astryxdesign/core/HStack'
import {Icon} from '@astryxdesign/core/Icon'
import {List, ListItem} from '@astryxdesign/core/List'
import {Section} from '@astryxdesign/core/Section'
import {Tab, TabList} from '@astryxdesign/core/TabList'
import {Text} from '@astryxdesign/core/Text'
import {Thumbnail} from '@astryxdesign/core/Thumbnail'
import {Token} from '@astryxdesign/core/Token'
import {VStack} from '@astryxdesign/core/VStack'
import {ArrowLeft, BarChart3, Gamepad2, History, Star, Trophy} from 'lucide-react'
import {gameArtwork, hasExactValorantRankAsset, rankAsset, valorantAgentAsset, valorantMapName} from '../assets'
import {CompetitiveInsights} from '../components/CompetitiveInsights'
import type {Match, Player, PlayerStats} from '../types'
import {AuthenticatedScreen, MatchList, RankMedia, rankLabel, rankRatingLabel} from './shared'

export interface PlayerProfileScreenProps {
  player: Player
  watched?: boolean
  /** Compatibility prop for callers that have not migrated to watched yet. */
  followed?: boolean
  onBack: () => void
  onSelectMatch: (match: Match) => void
  onToggleWatchlist?: () => void | Promise<void>
  /** Compatibility callback for callers that have not migrated yet. */
  onToggleFollow?: () => void | Promise<void>
}

const STAT_LABELS: Array<[keyof PlayerStats, string]> = [
  ['kills', 'Kills'],
  ['deaths', 'Deaths'],
  ['assists', 'Assists'],
  ['combatScore', 'Combat score'],
  ['damage', 'Damage'],
  ['headshots', 'Headshots'],
  ['gold', 'Gold'],
  ['minions', 'CS'],
  ['vision', 'Vision score'],
  ['level', 'Level'],
  ['placement', 'Placement'],
  ['playersEliminated', 'Players eliminated'],
]

function ProfileMetric({label, value, emblem}: {label: string; value: string; emblem?: string}) {
  useLocale()
  return (
    <Section className="pd-profile__metric" padding={0} variant="transparent">
      <HStack align="center" gap={3}>
        {emblem ? <Thumbnail alt={t("{{value}} rank emblem", {value: value})} className="peaks-media peaks-rank-media" label={value} src={emblem} /> : null}
        <VStack gap={2}>
          <Text type="supporting">{label}</Text>
          <Text type="large" weight="semibold">{displayText(value)}</Text>
        </VStack>
      </HStack>
    </Section>
  )
}

export function PlayerProfileScreen({
  player,
  watched,
  followed,
  onBack,
  onSelectMatch,
  onToggleWatchlist,
  onToggleFollow,
}: PlayerProfileScreenProps) {
  useLocale()
  const {displayName} = usePlayerPrivacy()
  const [tab, setTab] = useState(player.context ? 'performance' : 'activity')
  const isWatched = watched ?? followed ?? false
  const toggleWatchlist = onToggleWatchlist ?? onToggleFollow
  const ranks = player.ranks?.filter(rank => rank.tier.trim()) ?? []
  const stats = player.context?.stats ?? {}
  const statRows = STAT_LABELS.flatMap(([key, label]) => {
    const value = stats[key]
    return value == null ? [] : [{key, label, value}]
  })
  return (
    <AuthenticatedScreen
      actions={
        <Button
          className={isWatched ? 'peaks-watch-button peaks-watch-button--selected' : 'peaks-watch-button'}
          clickAction={async () => { await toggleWatchlist?.() }}
          icon={<Icon icon={Star} />}
          label={isWatched ? t("Unwatch") : t("Watch")}
          variant={isWatched ? 'secondary' : 'primary'}
        />
      }
      description={`${player.region} · ${displayText(player.game ?? 'Riot profile')}${player.lastUpdated ? ` · ${displayText(player.lastUpdated)}` : ''}`}
      screen="player-profile"
      title={t("Player profile")}>
      <VStack className="pd-detail pd-profile" gap={6}>
        <HStack align="center" justify="between" gap={3}>
          <Button icon={<Icon icon={ArrowLeft} />} label={t("Back")} onClick={onBack} size="sm" variant="ghost" />
          <Text className="pd-detail__eyebrow" type="supporting">{player.region}</Text>
        </HStack>

        <Grid className="pd-detail__identity" columns={2} gap={0}>
          <VStack className="pd-detail__identity-copy" gap={8} justify="between" padding={8}>
            <HStack align="center" gap={3} justify="between" wrap="wrap">
              <Text className="pd-detail__eyebrow" type="supporting">{player.game ?? t("RIOT GAMES")} {t("/ PLAYER PROFILE")}</Text>
              {isWatched ? <Token color="gray" label={t("On your watchlist")} size="sm" /> : null}
            </HStack>
            <VStack gap={4}>
              <Avatar
                className="pd-detail__avatar"
                name={displayName(player.riotId)}
                size="lg"
                src={player.game === 'VALORANT' ? valorantAgentAsset(player.context?.character) : undefined}
                tooltip={false}
              />
                <Heading className="pd-detail__identity-name" level={2} type="display-2">{displayName(player.riotId)}</Heading>
                <HStack align="center" gap={3} wrap="wrap">
                  <Token color="gray" label={player.region} size="sm" />
                  {player.level != null ? <Text color="secondary">{t("Level")} {player.level}</Text> : null}
                  {player.context?.character ? <Text color="secondary">{player.context.character}</Text> : null}
                </HStack>
            </VStack>
          </VStack>
          <Section className="pd-detail__identity-art pd-detail__art" padding={8} variant="transparent" style={player.game ? {backgroundImage: `url("${gameArtwork(player.game, player.context?.map ?? player.matches?.[0]?.map)}")`} : undefined}>
            <VStack className="pd-detail__art-content" justify="end" align="end" gap={2}>
              <Text className="pd-detail__eyebrow" type="supporting">{player.context?.map ? t("LAST ENCOUNTER") : t("COMPETITIVE PROFILE")}</Text>
              <Heading level={3} type="display-3">{player.context?.map ? (player.game === 'VALORANT' ? valorantMapName(player.context.map) : player.context.map) : player.game ?? t("Riot Games")}</Heading>
              {player.context?.label || player.lastGame ? <Text type="supporting">{displayText(player.context?.label ?? player.lastGame)}</Text> : null}
            </VStack>
          </Section>
        </Grid>

        <Grid className="pd-detail__workspace" columns={2} gap={8}>
          <VStack className="pd-detail__sidebar" gap={5}>
            <HStack align="center" gap={2}><Icon icon={Trophy} color="secondary" /><Heading level={2}>{t("Competitive record")}</Heading></HStack>
            {ranks.length > 0 ? <List aria-label={t("Current ranks")} density="balanced" hasDividers>
              {ranks.map(rank => <ListItem
                description={displayText(rankLabel(rank))}
                endContent={rank.rating != null ? <Text hasTabularNumbers weight="semibold">{rankRatingLabel(rank.game, rank.rating)}</Text> : undefined}
                key={rank.game}
                label={rank.game}
                startContent={<RankMedia rank={rank} />}
              />)}
            </List> : <>
              <ProfileMetric
                emblem={player.game === 'VALORANT' && player.currentRank && hasExactValorantRankAsset(player.currentRank) ? rankAsset('VALORANT', player.currentRank) : undefined}
                label={t("CURRENT RANK")}
                value={player.currentRank?.trim() || 'Rank unavailable'}
              />
              <ProfileMetric
                emblem={player.game === 'VALORANT' && player.peakRank && hasExactValorantRankAsset(player.peakRank) ? rankAsset('VALORANT', player.peakRank) : undefined}
                label={t("CAREER PEAK")}
                value={player.peakRank?.trim() || 'Rank unavailable'}
              />
            </>}
            <ProfileMetric label={t("LAST SEEN")} value={player.lastGame ?? player.context?.label ?? 'Unknown'} />
          </VStack>

          <VStack className="pd-detail__main" gap={6}>
            <TabList className="pd-detail__tabs" aria-label={t("Player profile views")} hasDivider onChange={setTab} role="tablist" value={tab}>
              <Tab icon={<Icon icon={History} />} label={t("Activity")} panelId="profile-activity-panel" value="activity" />
              <Tab icon={<Icon icon={BarChart3} />} label={t("Performance")} panelId="profile-performance-panel" value="performance" />
            </TabList>

            {tab === 'activity' ? <VStack className="pd-detail__panel" aria-label={t("Activity")} gap={5} id="profile-activity-panel" role="tabpanel"><MatchList heading={t("Recent matches")} matches={player.matches ?? []} onSelect={onSelectMatch} /></VStack> : null}

            {tab === 'performance' ? <VStack className="pd-detail__panel" aria-label={t("Performance")} gap={6} id="profile-performance-panel" role="tabpanel">

        {player.context ? (
          <Section padding={0} variant="transparent">
            <List
              className="peaks-dense-list peaks-profile-stat-list"
              density="compact"
              hasDividers
              header={<HStack align="center" justify="between" gap={3}><Heading level={2}>{t("Match performance")}</Heading><Text type="supporting">{displayText(player.context.label)}</Text></HStack>}>
              <ListItem
                description={`${displayText(player.context.team ?? 'Team unavailable')} · ${displayText(player.context.character ?? 'Character unavailable')}`}
                endContent={<Text hasTabularNumbers weight="semibold">{player.context.score ?? '—'}</Text>}
                label={player.context.map && player.game === 'VALORANT' ? valorantMapName(player.context.map) : player.context.map ?? player.context.label}
                startContent={<Icon color="secondary" icon={Gamepad2} />}
              />
              {statRows.map(row => (
                <ListItem
                  endContent={<Text hasTabularNumbers weight="semibold">{row.value.toLocaleString()}</Text>}
                  key={row.key}
                  label={t(row.label)}
                />
              ))}
            </List>
          </Section>
        ) : null}

        {(player.matches ?? []).length > 0 ? (
          <VStack gap={6}>
            <CompetitiveInsights matches={player.matches ?? []} riotId={player.riotId} />
          </VStack>
        ) : null}
        {!player.context && (player.matches ?? []).length === 0 ? <EmptyState icon={<Icon icon={BarChart3} />} title={t("No match data available")} description={t("Performance details appear when matches are available for this player.")} /> : null}
          </VStack> : null}
          </VStack>
        </Grid>
      </VStack>
    </AuthenticatedScreen>
  )
}
