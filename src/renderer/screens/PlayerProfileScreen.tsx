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
import {Skeleton} from '@astryxdesign/core/Skeleton'
import {Tab, TabList} from '@astryxdesign/core/TabList'
import {Text} from '@astryxdesign/core/Text'
import {Token} from '@astryxdesign/core/Token'
import {VStack} from '@astryxdesign/core/VStack'
import {ArrowLeft, BarChart3, Gamepad2, History, Star, Trophy} from 'lucide-react'
import {valorantMapName} from '../assets'
import {CompetitiveInsights} from '../components/CompetitiveInsights'
import {mergeRiotProfile} from '../playerProfiles'
import type {Match, Player, PlayerStats} from '../types'
import {AuthenticatedScreen, GAMES, MatchList, RankMedia, rankLabel, rankRatingLabel} from './shared'

export interface PlayerProfileScreenProps {
  player: Player
  isLoading?: boolean
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

function ProfileMetric({label, value}: {label: string; value: string}) {
  useLocale()
  return (
    <Section className="pd-profile__metric" padding={0} variant="transparent">
      <VStack gap={2}>
        <Text type="supporting">{label}</Text>
        <Text type="large" weight="semibold">{displayText(value)}</Text>
      </VStack>
    </Section>
  )
}

export function PlayerProfileScreen({
  player,
  isLoading = false,
  watched,
  followed,
  onBack,
  onSelectMatch,
  onToggleWatchlist,
  onToggleFollow,
}: PlayerProfileScreenProps) {
  useLocale()
  const {displayName} = usePlayerPrivacy()
  const [tab, setTab] = useState('activity')
  const isWatched = watched ?? followed ?? false
  const toggleWatchlist = onToggleWatchlist ?? onToggleFollow
  const profile = mergeRiotProfile(player, [], [])
  const games = GAMES.filter(game => profile.games?.includes(game))
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
      description={`${player.region}${player.lastUpdated ? ` · ${displayText(player.lastUpdated)}` : ''}`}
      screen="player-profile"
      title={t("Riot profile")}>
      <VStack className="pd-detail pd-profile" gap={6}>
        <HStack align="center" justify="between" gap={3}>
          <Button icon={<Icon icon={ArrowLeft} />} label={t("Back")} onClick={onBack} size="sm" variant="ghost" />
          <Text className="pd-detail__eyebrow" type="supporting">{player.region}</Text>
        </HStack>

        <Section className="pd-profile__identity pd-riot-surface" padding={6} variant="transparent">
          <HStack align="center" gap={6} justify="between" wrap="wrap">
            <HStack align="center" gap={6}>
              <Avatar
                className="pd-detail__avatar"
                name={displayName(player.riotId)}
                size="lg"
                tooltip={false}
              />
              <VStack gap={3}>
                <Text className="pd-detail__eyebrow" type="supporting">RIOT ID</Text>
                <Heading className="pd-detail__identity-name" level={2} type="display-2">{displayName(player.riotId)}</Heading>
                <Text color="secondary">{player.region}</Text>
              </VStack>
            </HStack>
            {isWatched ? <Token color="gray" label={t("On your watchlist")} size="sm" /> : null}
          </HStack>
        </Section>

        <Grid className="pd-detail__workspace" columns={2} gap={8}>
          <VStack className="pd-detail__sidebar" gap={5}>
            <HStack align="center" gap={2}><Icon icon={Trophy} color="secondary" /><Heading level={2}>{t("Competitive record")}</Heading></HStack>
            {games.length > 0 ? <List aria-label={t("Current ranks")} aria-busy={isLoading} density="balanced" hasDividers>
              {games.map(game => {
                const rank = profile.ranks?.find(item => item.game === game)
                const peak = profile.peakRanks?.find(item => item.game === game)
                return <ListItem key={game} label={game}
                  description={<VStack gap={1}>
                    {rank ? <Text type="supporting">{displayText(rankLabel(rank))}{rank.rating != null ? ` · ${rankRatingLabel(game, rank.rating)}` : ''}</Text>
                      : isLoading ? <Skeleton width="var(--spacing-24)" height="var(--spacing-3)" /> : <Text type="supporting">{t('Rank unavailable')}</Text>}
                    {peak ? <Text type="supporting">{t('Peak')} · {displayText(rankLabel(peak))}</Text> : null}
                    {player.game === game && player.level != null ? <Text type="supporting">{t('Level {{level}}', {level: player.level})}</Text> : null}
                  </VStack>}
                  startContent={rank ? <RankMedia rank={rank} /> : <Icon icon={Trophy} color="secondary" />}
                />
              })}
            </List> : isLoading ? <Skeleton width="100%" height="var(--spacing-12)" /> : <Text color="secondary">{t('Rank unavailable')}</Text>}
            <ProfileMetric label={t("LAST SEEN")} value={player.lastGame ?? player.context?.label ?? 'Unknown'} />
          </VStack>

          <VStack className="pd-detail__main" gap={6}>
            <TabList className="pd-detail__tabs" aria-label={t("Player profile views")} hasDivider onChange={setTab} role="tablist" value={tab}>
              <Tab icon={<Icon icon={History} />} label={t("Activity")} panelId="profile-activity-panel" value="activity" />
              <Tab icon={<Icon icon={BarChart3} />} label={t("Performance")} panelId="profile-performance-panel" value="performance" />
            </TabList>

            {tab === 'activity' ? <VStack className="pd-detail__panel" aria-label={t("Activity")} gap={5} id="profile-activity-panel" role="tabpanel">
              {isLoading && !player.matches?.length ? <VStack aria-label={t('Loading')} aria-busy gap={4}>{[0, 1, 2].map(index => <Skeleton key={index} index={index} width="100%" height="var(--spacing-12)" />)}</VStack> : <MatchList heading={t("Recent matches")} matches={player.matches ?? []} onSelect={onSelectMatch} />}
            </VStack> : null}

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
