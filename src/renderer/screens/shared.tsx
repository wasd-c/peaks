import {t, useLocale, displayText} from '../i18n'
import type {ReactNode} from 'react'
import {Avatar} from '@astryxdesign/core/Avatar'
import {Button} from '@astryxdesign/core/Button'
import {Card} from '@astryxdesign/core/Card'
import {EmptyState} from '@astryxdesign/core/EmptyState'
import {Heading} from '@astryxdesign/core/Heading'
import {HStack} from '@astryxdesign/core/HStack'
import {Icon} from '@astryxdesign/core/Icon'
import {Layout, LayoutContent, LayoutHeader} from '@astryxdesign/core/Layout'
import {List, ListItem} from '@astryxdesign/core/List'
import {ProgressBar} from '@astryxdesign/core/ProgressBar'
import {StatusDot} from '@astryxdesign/core/StatusDot'
import {Text} from '@astryxdesign/core/Text'
import {Thumbnail} from '@astryxdesign/core/Thumbnail'
import {Token} from '@astryxdesign/core/Token'
import {VStack} from '@astryxdesign/core/VStack'
import {ChevronRight, Gamepad2, Star, Trophy} from 'lucide-react'
import {gameArtwork, hasExactValorantRankAsset, rankAsset, valorantAgentAsset, valorantAgentName, valorantMapName} from '../assets'
import type {Account, Game, Match, Player, Rank} from '../types'
import {usePlayerPrivacy} from '../components/PlayerPrivacy'

export type AuthenticatedView = 'grid' | 'list'
export type ActionCallback = (command: string, payload?: unknown, propagateError?: boolean) => Promise<void>
export type InvokeCallback = <T>(command: string, payload?: unknown) => Promise<T>

export const GAMES: readonly Game[] = [
  'League of Legends',
  'VALORANT',
  'Teamfight Tactics',
]

const RANK_ORDER = [
  'unranked',
  'iron',
  'bronze',
  'silver',
  'gold',
  'platinum',
  'emerald',
  'diamond',
  'master',
  'grandmaster',
  'challenger',
  'ascendant',
  'immortal',
  'radiant',
]

export function titleCase(value: string) {
  return value
    .trim()
    .split(/\s+/)
    .map(part => `${part.charAt(0).toUpperCase()}${part.slice(1).toLowerCase()}`)
    .join(' ')
}

export function shortGame(game: Game) {
  if (game === 'League of Legends') return 'LEAGUE'
  if (game === 'Teamfight Tactics') return 'TFT'
  return 'VALORANT'
}

export function rankRatingLabel(game: Game, rating: number) {
  return `${rating} ${game === 'VALORANT' ? 'RR' : 'LP'}`
}

export function rankLabel(rank?: Rank) {
  if (!rank || rank.tier.toLowerCase() === 'unranked') return 'Unranked'
  const tier = titleCase(rank.tier).replace(/\b[ivx]+\b/gi, part => part.toUpperCase())
  return `${tier}${rank.division ? ` ${rank.division.toUpperCase()}` : ''}`
}

export function rankScore(rank: Rank) {
  return RANK_ORDER.indexOf(rank.tier.trim().toLowerCase().split(/\s+/)[0])
}

type TokenColor = 'default' | 'red' | 'orange' | 'yellow' | 'green' | 'teal' | 'cyan' | 'blue' | 'purple' | 'pink' | 'gray'

export function rankColor(rank?: Rank): TokenColor {
  const tier = rank?.tier.trim().toLowerCase().split(/\s+/)[0] ?? 'unranked'
  if (tier === 'iron' || tier === 'unranked') return 'gray'
  if (tier === 'bronze') return 'orange'
  if (tier === 'silver') return 'cyan'
  if (tier === 'gold' || tier === 'radiant') return 'yellow'
  if (tier === 'platinum') return 'teal'
  if (tier === 'emerald' || tier === 'ascendant') return 'green'
  if (tier === 'diamond') return 'blue'
  if (tier === 'immortal' || tier === 'grandmaster') return 'red'
  if (tier === 'master' || tier === 'challenger') return 'purple'
  return 'pink'
}

export function resultColor(result: string): TokenColor {
  const normalized = result.trim().toLowerCase()
  if (normalized === 'win' || normalized === 'victory' || normalized === 'top 4') return 'green'
  if (normalized === 'loss' || normalized === 'defeat') return 'red'
  if (normalized === 'draw' || normalized === 'placement') return 'yellow'
  return 'gray'
}

export function strongestRank(accounts: Account[]) {
  return accounts
    .flatMap(account => account.ranks)
    .reduce<Rank | undefined>(
      (strongest, rank) => !strongest || rankScore(rank) > rankScore(strongest) ? rank : strongest,
      undefined,
    )
}

export function primaryAccountRank(account: Account) {
  return strongestRank([account]) ?? account.ranks[0]
}

interface AuthenticatedScreenProps {
  title: string
  description?: string
  eyebrow?: string
  actions?: ReactNode
  children: ReactNode
  screen: string
  contentWidth?: number | string
}

export function AuthenticatedScreen({
  title,
  description,
  eyebrow,
  actions,
  children,
  screen,
  contentWidth = 'var(--peaks-content-width)',
}: AuthenticatedScreenProps) {
  useLocale()
  return (
    <Layout
      className={`peaks-screen peaks-screen--enter peaks-screen--${screen}`}
      contentWidth={contentWidth}
      padding={8}
      header={
        <LayoutHeader padding={0}>
          <HStack
            align="center"
            className="peaks-screen__header"
            gap={4}
            paddingInline={8}
            paddingBlock={6}
            justify="between">
            <VStack gap={1}>
              {eyebrow ? <Text className="peaks-eyebrow" type="supporting">{eyebrow}</Text> : null}
              <Heading level={1} textWrap="balance">{title}</Heading>
              {description ? <Text color="secondary">{description}</Text> : null}
            </VStack>
            {actions ? (
              <HStack align="center" className="peaks-screen__actions" gap={2}>
                {actions}
              </HStack>
            ) : null}
          </HStack>
        </LayoutHeader>
      }
      content={
        <LayoutContent className="peaks-screen__content">
          {children}
        </LayoutContent>
      }
    />
  )
}

export function RankMedia({rank}: {rank?: Rank}) {
  useLocale()
  if (!rank) {
    return <Icon icon={Trophy} color="secondary" label={t("Unranked")} />
  }

  if (rank.game !== 'VALORANT' && rank.tier.toLowerCase() === 'unranked') {
    return <Icon icon={Trophy} color="secondary" label={t("Unranked")} />
  }

  const label = rankLabel(rank)
  if (rank.game === 'VALORANT' && rank.tier.toLowerCase() !== 'unranked' && !hasExactValorantRankAsset(label)) {
    return <Icon icon={Trophy} color="secondary" label={t("{{label}} · division unavailable", {label: displayText(label)})} />
  }

  return (
    <Thumbnail
      alt={t("{{label}} rank emblem", {label: displayText(label)})}
      className="peaks-media peaks-rank-media"
      label={t("{{label}} rank emblem", {label: displayText(label)})}
      src={rankAsset(rank.game, label)}
    />
  )
}

export function RankCard({game, rank}: {game: Game; rank?: Rank}) {
  useLocale()
  const rating = Math.max(0, Math.min(100, rank?.rating ?? 0))
  return (
    <Card className="peaks-rank-card" padding={5} variant="muted">
      <VStack gap={4}>
        <HStack align="center" gap={3}>
          <RankMedia rank={rank} />
          <VStack gap={0.5}>
            <Text className="peaks-eyebrow" type="supporting">{shortGame(game)}</Text>
            <Heading level={3}>{displayText(rankLabel(rank))}</Heading>
            <Text color="secondary">
              {rank?.rating != null
                ? rankRatingLabel(game, rank.rating)
                : t("Awaiting competitive placement")}
            </Text>
          </VStack>
        </HStack>
        <ProgressBar
          isLabelHidden
          label={t("{{game}} rank progress", {game: game})}
          max={100}
          value={rating}
          variant={rank && rank.tier.toLowerCase() !== 'unranked' ? 'accent' : 'neutral'}
        />
      </VStack>
    </Card>
  )
}

export function AccountListItem({account, onSelect}: {account: Account; onSelect: (account: Account) => void}) {
  useLocale()
  const {displayName} = usePlayerPrivacy()
  const rank = primaryAccountRank(account)
  const connectionLabel = account.connected ? 'Connected' : 'Offline'
  return (
    <ListItem
      description={t("{{region}} · Level {{value2}} · {{value3}}", {region: account.region, value2: account.level ?? '—', value3: displayText(rankLabel(rank))})}
      endContent={
        <HStack align="center" gap={3}>
          <StatusDot label={t(connectionLabel)} variant={account.connected ? 'success' : 'neutral'} />
          <Text type="supporting">{t(connectionLabel)}</Text>
          <Icon icon={ChevronRight} color="secondary" />
        </HStack>
      }
      label={displayName(account.riotId)}
      onClick={() => onSelect(account)}
      startContent={<Avatar name={displayName(account.riotId)} size="lg" tooltip={false} />}
    />
  )
}

export function PlayerListItem({
  player,
  action,
  onSelect,
}: {
  player: Player
  action: ActionCallback
  onSelect?: (player: Player) => void
}) {
  useLocale()
  const watched = player.followed === true
  const {displayName} = usePlayerPrivacy()
  const ranks = player.ranks?.filter(rank => rank.tier.trim()) ?? []
  return (
    <ListItem
      description={
        <VStack gap={2}>
          <Text type="supporting">{`${player.region} · ${displayText(player.game ?? 'Riot profile')}${player.lastUpdated ? ` · ${displayText(player.lastUpdated)}` : ''}`}</Text>
          {ranks.length > 0 ? <HStack align="start" gap={4} wrap="wrap">
            {ranks.map(rank => <HStack align="center" gap={2} key={rank.game}>
              <RankMedia rank={rank} />
              <VStack gap={0.5}>
                <Text type="supporting">{rank.game}</Text>
                <Text weight="semibold">{displayText(rankLabel(rank))}</Text>
                {rank.rating != null ? <Text hasTabularNumbers type="supporting">{rankRatingLabel(rank.game, rank.rating)}</Text> : null}
              </VStack>
            </HStack>)}
          </HStack> : null}
        </VStack>
      }
      endContent={
        <HStack align="center" className="peaks-player-row__metadata" gap={4}>
          {ranks.length === 0 ? <>
            <VStack gap={0.5}>
              <Text type="supporting">{t("CURRENT")}</Text>
              <Text weight="semibold">{displayText(player.currentRank?.trim() || 'Rank unavailable')}</Text>
            </VStack>
            <VStack gap={0.5}>
              <Text type="supporting">{t("PEAK")}</Text>
              <Text weight="semibold">{displayText(player.peakRank?.trim() || 'Rank unavailable')}</Text>
            </VStack>
          </> : null}
          <Button
            className={watched ? 'peaks-watch-button peaks-watch-button--selected' : 'peaks-watch-button'}
            clickAction={() => action('toggle_watchlist', {player})}
            icon={<Icon icon={Star} />}
            isIconOnly
            label={watched ? t("Unwatch {{value1}}", {value1: displayName(player.riotId)}) : t("Watch {{value1}}", {value1: displayName(player.riotId)})}
            size="sm"
            tooltip={watched ? t("Unwatch player") : t("Watch player")}
            variant="ghost"
          />
          {onSelect ? <Icon color="secondary" icon={ChevronRight} /> : null}
        </HStack>
      }
      label={displayName(player.riotId)}
      onClick={onSelect ? () => onSelect(player) : undefined}
      startContent={<Avatar name={displayName(player.riotId)} size="lg" tooltip={false} />}
    />
  )
}

export function PlayerList({
  players,
  action,
  heading,
  onSelect,
}: {
  players: Player[]
  action: ActionCallback
  heading: string
  onSelect?: (player: Player) => void
}) {
  useLocale()
  return (
    <List
      className="peaks-dense-list peaks-player-list"
      density="balanced"
      hasDividers
      header={<Heading level={2}>{displayText(heading)}</Heading>}>
      {players.map(player => (
        <PlayerListItem action={action} key={player.id} onSelect={onSelect} player={player} />
      ))}
    </List>
  )
}

export function MatchList({
  matches,
  heading = 'Recent matches',
  onSelect,
}: {
  matches: Match[]
  heading?: string | null
  onSelect?: (match: Match) => void
}) {
  useLocale()
  if (matches.length === 0) {
    return (
      <EmptyState
        description={t("Match history appears after the next sync.")}
        icon={<Icon icon={Gamepad2} color="secondary" />}
        title={t("No recent matches")}
      />
    )
  }

  return (
    <List
      className="peaks-dense-list peaks-match-list"
      density="compact"
      hasDividers
      aria-label={displayText(heading ?? 'Recent matches')}
      header={heading ? <Heading level={2}>{displayText(heading)}</Heading> : undefined}>
      {matches.map((match, index) => {
        const agent = match.teams?.flatMap(team => team.players).find(player => player.self)?.agent || match.agent
        const agentName = match.game === 'VALORANT' ? valorantAgentName(agent) : agent
        const agentIcon = match.game === 'VALORANT' ? valorantAgentAsset(agent) : undefined
        const mapName = match.game === 'VALORANT' ? valorantMapName(match.map) : match.map || match.game
        return (
        <ListItem
          description={
            <HStack align="center" gap={2} wrap="wrap">
              {agentName ? <HStack align="center" gap={1.5}>{agentIcon ? <Avatar name={agentName} src={agentIcon} size="sm" tooltip={false} /> : null}<Text type="supporting" weight="medium">{agentName}</Text><Text type="supporting" color="secondary">·</Text></HStack> : null}
              <Text type="supporting" color="secondary">{`${displayText(titleCase(match.mode ?? 'Competitive'))} · ${match.duration ?? '—'}${match.playedAt ? ` · ${displayText(match.playedAt)}` : ''}`}</Text>
            </HStack>
          }
          endContent={
            <HStack align="center" gap={3}>
              <VStack align="end" gap={0.5}>
                <Text hasTabularNumbers weight="semibold">{match.score ?? '—'}</Text>
                <Text type="supporting">{displayText(match.delta ?? match.performance ?? match.mode ?? 'Competitive')}</Text>
              </VStack>
              {onSelect ? <Icon color="secondary" icon={ChevronRight} /> : null}
            </HStack>
          }
          key={match.id ?? `${match.game}-${index}`}
          label={mapName}
          onClick={onSelect ? () => onSelect(match) : undefined}
          startContent={
            <HStack align="center" gap={2}>
              <img className="peaks-match-thumbnail" src={gameArtwork(match.game, match.map)} alt="" />
              <Token color={resultColor(match.result)} label={displayText(match.result)} size="sm" />
            </HStack>
          }
        />
        )
      })}
    </List>
  )
}

export function EmptyAccounts({onAdd}: {onAdd: () => void}) {
  useLocale()
  return (
    <EmptyState
      actions={<Button label={t("Add your first account")} onClick={onAdd} />}
      description={t("Add a Riot account to view its ranks and recent matches.")}
      icon={<Icon icon={Trophy} color="secondary" />}
      title={t("No accounts yet")}
    />
  )
}
