import {t, useLocale, displayText} from '../i18n'
import {usePlayerPrivacy} from './PlayerPrivacy'
import {useMemo, useState} from 'react'
import {Avatar} from '@astryxdesign/core/Avatar'
import {EmptyState} from '@astryxdesign/core/EmptyState'
import {Grid} from '@astryxdesign/core/Grid'
import {Heading} from '@astryxdesign/core/Heading'
import {HStack} from '@astryxdesign/core/HStack'
import {Icon} from '@astryxdesign/core/Icon'
import {List, ListItem} from '@astryxdesign/core/List'
import {Section} from '@astryxdesign/core/Section'
import {Selector} from '@astryxdesign/core/Selector'
import {Text} from '@astryxdesign/core/Text'
import {Thumbnail} from '@astryxdesign/core/Thumbnail'
import {Token} from '@astryxdesign/core/Token'
import {VStack} from '@astryxdesign/core/VStack'
import {Activity, Crosshair, Map, TrendingUp, UsersRound} from 'lucide-react'

import {valorantAgentAsset, valorantMapAsset, valorantMapName} from '../assets'
import type {Match} from '../types'
import {valorantInsights, type PerformanceBreakdown} from '../valorantInsights'
import {resultColor} from '../screens/shared'
import {PerformanceBreakdownPanel} from './MatchInsights'

export interface CompetitiveInsightsProps {
  matches: Match[]
  riotId: string
}

const decimal = (value?: number) => value == null ? '—' : value.toFixed(2)
const whole = (value?: number) => value == null ? '—' : String(Math.round(value))
const percentage = (value?: number) => value == null ? '—' : `${Math.round(value)}%`

function Metric({label, value, description}: {label: string; value: string; description: string}) {
  useLocale()
  return (
    <Section padding={5} variant="transparent">
      <VStack gap={2}>
        <Text type="supporting">{label}</Text>
        <Text className="peaks-metric-value" hasTabularNumbers type="display-3" weight="semibold">{value}</Text>
        <Text type="supporting">{description}</Text>
      </VStack>
    </Section>
  )
}

function BreakdownList({heading, rows, icon}: {
  heading: string
  rows: PerformanceBreakdown[]
  icon: typeof Crosshair
}) {
  useLocale()
  return (
    <Section padding={0} variant="transparent">
      <List
        className="peaks-dense-list peaks-insight-list"
        density="compact"
        hasDividers
        header={
          <HStack align="center" gap={2}>
            <Icon color="secondary" icon={icon} />
            <Heading level={2}>{heading}</Heading>
          </HStack>
        }>
        {rows.slice(0, 8).map(row => (
          <ListItem
            description={t("{{games}} matches · {{wins}}W {{losses}}L · {{value4}} K/D{{value5}}", {games: row.games, wins: row.wins, losses: row.losses, value4: decimal(row.kd), value5: row.averageCombatScore == null ? '' : ` · ${Math.round(row.averageCombatScore)} ACS`})}
            endContent={
              <VStack align="end" gap={0.5}>
                <Text hasTabularNumbers weight="semibold">{percentage(row.winRate)}</Text>
                <Text type="supporting">{t("WIN RATE")}</Text>
              </VStack>
            }
            key={row.label}
            label={icon === Map ? valorantMapName(row.label) : row.label}
            startContent={icon === Map ? (
              <Thumbnail alt={t("{{value1}} map", {value1: valorantMapName(row.label)})} className="peaks-media peaks-insight-map" label={valorantMapName(row.label)} src={valorantMapAsset(row.label)} />
            ) : (
              <Avatar name={row.label} size="lg" src={valorantAgentAsset(row.label)} tooltip={false} />
            )}
          />
        ))}
      </List>
    </Section>
  )
}

export function CompetitiveInsights({matches, riotId}: CompetitiveInsightsProps) {
  const language = useLocale()
  const {displayName} = usePlayerPrivacy()
  const [queue, setQueue] = useState('all')
  const [windowSize, setWindowSize] = useState('20')
  const queueOptions = useMemo(() => [
    {label: t('All queues', {lng: language}), value: 'all'},
    ...[...new Set(
      matches
        .filter(match => match.game === 'VALORANT')
        .map(match => match.mode?.trim())
        .filter((value): value is string => Boolean(value)),
    )].map(value => ({label: displayText(value), value})),
  ], [matches, language])
  const selectedMatches = useMemo(() => matches
    .filter(match => match.game === 'VALORANT')
    .filter(match => queue === 'all' || match.mode === queue)
    .slice(0, Number(windowSize)), [matches, queue, windowSize])
  const insights = valorantInsights(selectedMatches, riotId)
  if (!matches.some(match => match.game === 'VALORANT')) {
    return (
      <EmptyState
        description={t("Refresh the account after playing VALORANT to see win rate, agent performance, and recent form.")}
        icon={<Icon color="secondary" icon={Activity} />}
        title={t("No VALORANT performance data yet")}
      />
    )
  }

  const rrDelta = insights.rrDelta == null
    ? '—'
    : `${insights.rrDelta > 0 ? '+' : ''}${insights.rrDelta} RR`
  return (
    <VStack className="peaks-competitive-insights" gap={6}>
      <HStack align="end" gap={3} justify="between" wrap="wrap">
        <VStack gap={0.5}>
          <Text type="supporting">{t("VALORANT / PERFORMANCE")}</Text>
          <Heading level={2}>{t("Match performance")}</Heading>
          <Text color="secondary">{t('{{matches}} matches · {{wins}} wins · {{losses}} losses', {matches: insights.matches, wins: insights.wins, losses: insights.losses})}</Text>
        </VStack>
        <HStack align="end" gap={2}>
          <Selector
            label={t("Queue")}
            onChange={setQueue}
            options={queueOptions}
            size="sm"
            value={queue}
          />
          <Selector
            label={t("Matches")}
            onChange={setWindowSize}
            options={[
              {label: t('Last {{count}}', {count: 5}), value: '5'},
              {label: t('Last {{count}}', {count: 10}), value: '10'},
              {label: t('Last {{count}}', {count: 20}), value: '20'},
            ]}
            size="sm"
            value={windowSize}
          />
        </HStack>
      </HStack>
      <Grid
        className="peaks-metric-grid peaks-insight-metrics peaks-stat-strip"
        columns={{minWidth: 220, max: 3}}
        gap={0}>
        <Metric description={t("{{wins}} wins in this window", {wins: insights.wins})} label={t("WIN RATE")} value={percentage(insights.winRate)} />
        <Metric description={t("Kills per death")} label={t("K / D")} value={decimal(insights.kd)} />
        <Metric description={t("Average combat score")} label={t("COMBAT SCORE")} value={whole(insights.averageCombatScore)} />
        <Metric description={t("Average damage per round")} label={t("DAMAGE / ROUND")} value={whole(insights.averageDamagePerRound)} />
        <Metric description={t("Share of landed shots")} label={t("HEADSHOTS")} value={percentage(insights.headshotRate)} />
        <Metric description={t("Net rating change")} label={t("RANK MOVEMENT")} value={rrDelta} />
      </Grid>

      <PerformanceBreakdownPanel matches={selectedMatches} riotId={riotId} />

      <Grid className="peaks-insight-grid" columns={{minWidth: 320, max: 2}} gap={4}>
        <BreakdownList heading={t("Agent performance")} icon={Crosshair} rows={insights.agents} />
        <BreakdownList heading={t("Map performance")} icon={Map} rows={insights.maps} />
      </Grid>

      <Section padding={0} variant="transparent">
        <List
          className="peaks-dense-list peaks-insight-list"
          density="compact"
          hasDividers
          header={
            <HStack align="center" gap={2}>
              <Icon color="secondary" icon={TrendingUp} />
              <Heading level={2}>{t("Recent form")}</Heading>
            </HStack>
          }>
          {insights.trend.map(match => (
            <ListItem
              description={`${displayText(match.mode)}${match.playedAt ? ` · ${displayText(match.playedAt)}` : ''}${match.kda ? ` · ${match.kda} K/D/A` : ''}${match.averageCombatScore == null ? '' : ` · ${Math.round(match.averageCombatScore)} ACS`}`}
              endContent={
                <HStack align="center" gap={3}>
                  {match.rrDelta == null ? null : (
                    <Text hasTabularNumbers weight="semibold">
                      {match.rrDelta > 0 ? '+' : ''}{match.rrDelta} RR
                    </Text>
                  )}
                  <Token color={resultColor(match.result)} label={displayText(match.result)} size="sm" />
                </HStack>
              }
              key={match.id}
              label={valorantMapName(match.map)}
              startContent={
                <Thumbnail alt={t("{{value1}} map", {value1: valorantMapName(match.map)})} className="peaks-media peaks-insight-map" label={valorantMapName(match.map)} src={valorantMapAsset(match.map)} />
              }
            />
          ))}
        </List>
      </Section>

      {insights.teammates.length > 0 ? (
        <Section padding={0} variant="transparent">
          <List
            className="peaks-dense-list peaks-insight-list"
            density="compact"
            hasDividers
            header={
              <HStack align="center" gap={2}>
                <Icon color="secondary" icon={UsersRound} />
                <Heading level={2}>{t("Teammate synergy")}</Heading>
              </HStack>
            }>
            {insights.teammates.map(teammate => (
              <ListItem
                description={t("{{games}} shared matches · {{wins}} wins", {games: teammate.games, wins: teammate.wins})}
                endContent={<Text hasTabularNumbers weight="semibold">{percentage(teammate.winRate)}</Text>}
                key={teammate.riotId}
                label={displayName(teammate.riotId)}
                startContent={<Avatar name={displayName(teammate.riotId)} size="md" tooltip={false} />}
              />
            ))}
          </List>
        </Section>
      ) : null}

      <Section padding={0} variant="transparent">
        <Text color="secondary">{t("Based on your saved match history. A dash means that statistic is unavailable.")}</Text>
      </Section>
    </VStack>
  )
}
