import {usePlayerPrivacy} from './PlayerPrivacy'
import {Avatar} from '@astryxdesign/core/Avatar'
import {Grid} from '@astryxdesign/core/Grid'
import {Heading} from '@astryxdesign/core/Heading'
import {HStack} from '@astryxdesign/core/HStack'
import {Icon} from '@astryxdesign/core/Icon'
import {List, ListItem} from '@astryxdesign/core/List'
import {ProgressBar} from '@astryxdesign/core/ProgressBar'
import {Section} from '@astryxdesign/core/Section'
import {Text} from '@astryxdesign/core/Text'
import {Token} from '@astryxdesign/core/Token'
import {Tooltip} from '@astryxdesign/core/Tooltip'
import {VStack} from '@astryxdesign/core/VStack'
import {Crosshair, ScanLine, Sparkles, UsersRound} from 'lucide-react'
import {valorantAgentAsset} from '../assets'
import {matchAnalytics, playerPerformanceTags} from '../matchAnalytics'
import type {Game, Match, MatchPlayer} from '../types'

export function PlayerPerformanceTags({player, game}: {player: MatchPlayer; game: Game}) {
  const tags = playerPerformanceTags(player, game)
  if (tags.length === 0) return null
  return (
    <HStack className="peaks-player-performance-tags" align="center" gap={1} wrap="wrap">
      {tags.map(tag => (
        <Tooltip content={tag.detail} hasHoverIndication={false} key={tag.label}>
          <Token color="gray" description={tag.detail} label={tag.label} size="sm" />
        </Tooltip>
      ))}
    </HStack>
  )
}

export function MatchStandouts({match, riotId}: {match: Match; riotId?: string}) {
  const {displayName} = usePlayerPrivacy()
  if (match.game !== 'VALORANT') return null
  const owner = riotId?.trim().toLocaleLowerCase()
  const players = (match.teams ?? [])
    .flatMap(team => team.players)
    .filter(player => !player.hidden && !player.self
      && (!owner || (player.riotId ?? player.name).trim().toLocaleLowerCase() !== owner)
      && playerPerformanceTags(player, match.game).length > 0)
    .slice(0, 10)
  if (players.length === 0) return null

  return (
    <List
      className="peaks-dense-list peaks-match-standouts"
      density="compact"
      hasDividers
      header={
        <HStack align="center" gap={2}>
          <Icon color="secondary" icon={UsersRound} />
          <Heading level={2}>Around the lobby</Heading>
        </HStack>
      }>
      {players.map((player, index) => {
        const stats = player.stats
        const hasKda = stats && [stats.kills, stats.deaths, stats.assists].some(value => value != null)
        const kda = hasKda
          ? `${stats.kills ?? '—'} / ${stats.deaths ?? '—'} / ${stats.assists ?? '—'}`
          : player.score
        return (
          <ListItem
            description={
              <VStack gap={1}>
                <Text type="supporting">{player.agent ?? 'Agent unavailable'}</Text>
                <PlayerPerformanceTags game={match.game} player={player} />
              </VStack>
            }
            endContent={kda ? (
              <VStack align="end" gap={0.5}>
                <Text hasTabularNumbers weight="semibold">{kda}</Text>
                <Text type="supporting">K / D / A</Text>
              </VStack>
            ) : undefined}
            key={`${player.riotId ?? player.name}-${index}`}
            label={displayName(player.riotId ?? player.name)}
            startContent={<Avatar name={displayName(player.riotId ?? player.name)} size="md" src={valorantAgentAsset(player.agent)} tooltip={false} />}
          />
        )
      })}
    </List>
  )
}

export function PerformanceBreakdownPanel({matches, riotId}: {matches: Match[]; riotId?: string}) {
  const analytics = matchAnalytics(matches, riotId)
  return (
    <VStack className="peaks-match-insights" gap={5}>
      <VStack gap={3}>
        <HStack align="center" gap={2} justify="between" wrap="wrap">
          <HStack align="center" gap={2}>
            <Icon color="secondary" icon={ScanLine} />
            <Heading level={2}>Aim breakdown</Heading>
          </HStack>
          <Text type="supporting">
            {analytics.totalHits > 0 ? `${analytics.totalHits} landed hits${matches.length > 1 ? ` · ${analytics.hitMatches} matches with hit data` : ''}` : 'Hit-location data unavailable'}
          </Text>
        </HStack>
        <Grid className="peaks-stat-strip peaks-hit-distribution" columns={3} gap={0}>
          {analytics.hitDistribution.map(location => (
            <Section key={location.label} padding={4} variant="transparent">
              <VStack gap={2}>
                <Text type="supporting">{location.label.toUpperCase()}</Text>
                <Text className="peaks-metric-value" hasTabularNumbers type="display-3" weight="semibold">
                  {location.percentage == null ? '—' : `${location.percentage.toFixed(1)}%`}
                </Text>
                {location.percentage != null ? (
                  <ProgressBar
                    isLabelHidden
                    label={`${location.label}: share of landed hits`}
                    max={100}
                    value={location.percentage}
                    variant="neutral"
                  />
                ) : null}
                <Text type="supporting">{analytics.totalHits > 0 ? `${location.hits} hits` : 'Not available'}</Text>
              </VStack>
            </Section>
          ))}
        </Grid>
      </VStack>
      <Section padding={0} variant="transparent">
        <List
          className="peaks-dense-list peaks-weapon-list"
          density="compact"
          hasDividers
          header={
            <HStack align="center" gap={2} justify="between" wrap="wrap">
              <HStack align="center" gap={2}><Icon color="secondary" icon={Crosshair} /><Heading level={2}>Weapon usage</Heading></HStack>
              <Text type="supporting">SHARE OF RECORDED WEAPON KILLS</Text>
            </HStack>
          }>
          {analytics.weapons.length > 0 ? analytics.weapons.map(weapon => (
            <ListItem
              description={
                <VStack gap={2} paddingBlockEnd={1}>
                  <Text type="supporting">{weapon.kills} {weapon.kills === 1 ? 'kill' : 'kills'}</Text>
                  {weapon.percentage != null ? (
                    <ProgressBar
                      isLabelHidden
                      label={`${weapon.weapon}: share of recorded weapon kills`}
                      max={100}
                      value={weapon.percentage}
                      variant="neutral"
                    />
                  ) : null}
                </VStack>
              }
              endContent={<Text hasTabularNumbers weight="semibold">{Math.round(weapon.percentage ?? 0)}%</Text>}
              key={weapon.weapon}
              label={weapon.weapon}
              startContent={<Icon color="secondary" icon={Crosshair} />}
            />
          )) : (
            <ListItem
              description={analytics.weaponMatches > 0 ? 'No weapon kills were recorded in this window.' : 'Available when Riot returns the detailed match events.'}
              label={analytics.weaponMatches > 0 ? 'No recorded weapon kills' : 'Weapon details unavailable'}
              startContent={<Icon color="secondary" icon={Crosshair} />}
            />
          )}
        </List>
      </Section>
      <VStack gap={3}>
        <HStack align="center" gap={2}>
          <Icon color="secondary" icon={Sparkles} />
          <Heading level={2}>Performance tags</Heading>
        </HStack>
        {analytics.tags.length > 0 ? analytics.tags.map(tag => (
          <HStack align="center" gap={3} key={tag.label} wrap="wrap">
            <Token color="gray" label={tag.label} size="sm" />
            <Text color="secondary">{tag.detail}</Text>
          </HStack>
        )) : (
          <Text color="secondary">
            {analytics.roundMatches > 0 ? 'No standout round tags in this window.' : 'Round highlights appear when detailed match events are available.'}
          </Text>
        )}
      </VStack>
    </VStack>
  )
}

export function MatchInsights({match, riotId}: {match: Match; riotId?: string}) {
  return match.game === 'VALORANT' ? <PerformanceBreakdownPanel matches={[match]} riotId={riotId} /> : null
}
