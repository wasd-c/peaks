import {usePlayerPrivacy} from './PlayerPrivacy'
import {Button} from '@astryxdesign/core/Button'
import {Dialog, DialogHeader} from '@astryxdesign/core/Dialog'
import {Grid} from '@astryxdesign/core/Grid'
import {Heading} from '@astryxdesign/core/Heading'
import {HStack} from '@astryxdesign/core/HStack'
import {Icon} from '@astryxdesign/core/Icon'
import {Layout, LayoutContent, LayoutFooter} from '@astryxdesign/core/Layout'
import {Section} from '@astryxdesign/core/Section'
import {StatusDot} from '@astryxdesign/core/StatusDot'
import {Text} from '@astryxdesign/core/Text'
import {VStack} from '@astryxdesign/core/VStack'
import {ArrowUpRight, Clock3, Crosshair, Share2, Trophy} from 'lucide-react'
import {gameArtwork, rankAsset, valorantMapName} from '../assets'
import type {PostMatchReview} from '../postMatch'
import {rankLabel, titleCase} from '../screens/shared'
import {MatchInsights, MatchStandouts} from './MatchInsights'

interface PostMatchReviewDialogProps {
  review: PostMatchReview
  isOpen: boolean
  onDismiss: () => void
  onOpenReport: () => void
  onShare: () => void
}

function Metric({label, value}: {label: string; value: string}) {
  return (
    <VStack className="pd-recap__metric" gap={2} padding={5}>
      <Text className="pd-dialog__eyebrow" type="supporting">{label}</Text>
      <Text hasTabularNumbers type="display-3" weight="semibold">{value}</Text>
    </VStack>
  )
}

export function PostMatchReviewDialog({
  review, isOpen, onDismiss, onOpenReport, onShare,
}: PostMatchReviewDialogProps) {
  const {displayName} = usePlayerPrivacy()
  const {account, match} = review
  const self = match.teams?.flatMap(team => team.players).find(player => player.self && !player.hidden)
  const rank = account.ranks.find(value => value.game === match.game)
  const result = match.result.toLowerCase()
  const headline = result === 'win' || result === 'victory' ? 'Victory'
    : result === 'loss' ? 'Defeat' : result === 'recent match' ? 'Match complete' : match.result
  const map = match.game === 'VALORANT' ? valorantMapName(match.map) : match.map
  const kda = self?.stats?.kills != null && self.stats.deaths != null && self.stats.assists != null
    ? `${self.stats.kills} / ${self.stats.deaths} / ${self.stats.assists}` : self?.score ?? '—'
  const placement = self?.stats?.placement
  const combatScore = self?.stats?.combatScore
  const roundsPlayed = self?.stats?.roundsPlayed
  const averageCombatScore = combatScore != null && roundsPlayed != null && roundsPlayed > 0
    ? Math.round(combatScore / roundsPlayed) : null
  const secondaryStat = match.game === 'VALORANT'
    ? (averageCombatScore ?? combatScore)?.toLocaleString() ?? '—'
    : match.game === 'Teamfight Tactics' ? placement != null ? `#${placement}` : '—'
      : self?.stats?.minions?.toLocaleString() ?? '—'
  const secondaryLabel = match.game === 'VALORANT' ? averageCombatScore != null ? 'Combat score / round' : 'Combat score'
    : match.game === 'Teamfight Tactics' ? 'Placement' : 'Minions'
  const delta = match.delta != null && String(match.delta) !== '' ? String(match.delta) : null

  return (
    <Dialog
      className="pd-dialog pd-recap"
      isOpen={isOpen}
      maxHeight="calc(100dvh - var(--spacing-8))"
      onOpenChange={open => { if (!open) onDismiss() }}
      padding={0}
      purpose="info"
      width="calc(var(--spacing-12) * 19)">
      <Layout
        defaultHasDividers
        padding={6}
        style={{height: 'min(calc(var(--spacing-12) * 17), calc(100dvh - var(--spacing-8)))'}}
        header={
          <DialogHeader
            onOpenChange={open => { if (!open) onDismiss() }}
            startContent={<HStack className="pd-dialog__header-icon" align="center" justify="center"><Icon icon={Crosshair} /></HStack>}
            endContent={<HStack align="center" gap={2}><StatusDot label="Match recorded" variant="neutral" /><Text type="supporting">RECORDED</Text></HStack>}
            title="Match recap"
          />
        }
        content={
          <LayoutContent padding={0}>
            <VStack gap={0}>
              <Section
                className="pd-recap__hero"
                minHeight="calc(var(--spacing-12) * 6)"
                padding={8}
                variant="transparent">
                <img className="pd-recap__art" src={gameArtwork(match.game, match.map)} alt="" />
                <VStack className="pd-recap__hero-content" gap={6}>
                  <HStack align="center" justify="between" gap={4} wrap="wrap">
                    <Text className="pd-dialog__eyebrow" type="supporting">{match.game} / {titleCase(match.mode ?? 'Match')}</Text>
                    <HStack align="center" gap={2}><Icon icon={Clock3} size="sm" /><Text type="supporting">{match.playedAt ?? 'Just completed'}</Text></HStack>
                  </HStack>
                  <HStack align="end" gap={6} justify="between" wrap="wrap">
                    <VStack gap={2}>
                      <Heading className="pd-recap__result" level={2} type="display-1">{headline}</Heading>
                      <Text type="large">{map ?? 'Map unavailable'}</Text>
                    </VStack>
                    <VStack align="end" gap={1}>
                      <Text className="pd-dialog__eyebrow" type="supporting">FINAL SCORE</Text>
                      <Text className="pd-recap__score" hasTabularNumbers type="display-1" weight="semibold">{match.score ?? '—'}</Text>
                    </VStack>
                  </HStack>
                </VStack>
              </Section>
              <HStack className="pd-recap__identity" align="center" gap={4} justify="between" padding={5} wrap="wrap">
                <VStack gap={0.5}>
                  <Text className="pd-dialog__eyebrow" type="supporting">YOUR MATCH</Text>
                  <Text weight="semibold">{displayName(account.riotId)}</Text>
                </VStack>
                <HStack align="center" gap={3}>
                  {rank ? <img className="pd-recap__rank" src={rankAsset(rank.game, rankLabel(rank))} alt="" /> : <Icon icon={Trophy} color="secondary" />}
                  <VStack align="end" gap={0.5}>
                    <Text weight="semibold">{rankLabel(rank)}</Text>
                    {delta ? <Text type="supporting">{delta}</Text> : null}
                  </VStack>
                </HStack>
              </HStack>
              <Grid className="pd-recap__metrics" columns={3} gap={0}>
                <Metric label="K / D / A" value={kda} />
                <Metric label={secondaryLabel} value={secondaryStat} />
                <Metric label="Duration" value={match.duration ?? '—'} />
              </Grid>
              <Section className="pd-recap__analysis" padding={6} variant="transparent">
                <VStack gap={6}>
                  <MatchInsights match={match} riotId={account.riotId} />
                  <MatchStandouts match={match} riotId={account.riotId} />
                </VStack>
              </Section>
            </VStack>
          </LayoutContent>
        }
        footer={
          <LayoutFooter padding={6}>
            <HStack align="center" gap={3} justify="between" width="100%" wrap="wrap">
              <Button label="Back to Peaks" onClick={onDismiss} variant="ghost" />
              <HStack gap={2} wrap="wrap">
                <Button icon={<Icon icon={ArrowUpRight} />} label="Full match report" onClick={onOpenReport} />
                <Button icon={<Icon icon={Share2} />} label="Share this match" onClick={onShare} variant="primary" />
              </HStack>
            </HStack>
          </LayoutFooter>
        }
      />
    </Dialog>
  )
}
