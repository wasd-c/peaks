import type {ReactNode} from 'react'
import {Clock3, Heart, UsersRound} from 'lucide-react'
import {t} from '../i18n'
import {validNumber} from '../matchStatRows'
import {gameProfileIcon} from '../profileAssets'
import {Heading, HStack, Icon, StatusDot, Text, Tooltip, VStack} from '../ui'
import type {Game, MatchPlayer} from '../types'
import './liveMatch.css'

export function LiveMatchHeader({game, title, mode, elapsed, players, stale, score}: {
  game: Game
  title: string
  mode?: string
  elapsed?: string
  players: MatchPlayer[]
  stale?: boolean
  score: ReactNode
}) {
  const status = stale ? t('Awaiting update') : t('In game')
  const playerCount = players.length
  const health = players.map(player => player.hidden ? undefined : player.stats?.health)
  const alive = game === 'Teamfight Tactics' && playerCount >= 8 && health.every(validNumber)
    ? health.filter(value => value > 0).length : undefined
  const count = alive !== undefined ? t('{{alive}} / {{total}} alive', {alive, total: playerCount}) : t('{{count}} players in this session', {count: playerCount})
  return <HStack className="live-match-header" data-game={game} align="center" gap={4}>
    <HStack className="live-match-header__identity" align="center" gap={3}>
      <img src={gameProfileIcon(game)} alt={title === game ? '' : game} title={game} className="live-match-header__mark" />
      <VStack gap={0.5}>
        <Heading className="live-match-header__title" level={2}>{title}</Heading>
        {mode && mode !== title ? <Text className="live-match-header__mode" color="secondary">{mode}</Text> : null}
      </VStack>
    </HStack>
    {score ? <HStack className="live-match-header__score" justify="center">{score}</HStack> : null}
    <HStack className="live-match-header__telemetry" align="center" gap={4} wrap>
      {elapsed ? <Tooltip content={t('Elapsed time')}><HStack as="span" align="center" gap={1.5}><Icon icon={Clock3} size="sm" /><Text hasTabularNumbers>{elapsed}</Text></HStack></Tooltip> : null}
      <Tooltip content={count}><HStack as="span" aria-label={count} align="center" gap={1.5}><Icon icon={alive === undefined ? UsersRound : Heart} size="sm" /><Text hasTabularNumbers>{alive === undefined ? playerCount : `${alive}/${playerCount}`}</Text></HStack></Tooltip>
      <HStack className="live-match-header__status" data-stale={stale || undefined} align="center" gap={1.5}>
        <StatusDot variant={stale ? 'neutral' : 'success'} label={status} />
        {stale ? <Text>{status}</Text> : null}
      </HStack>
    </HStack>
  </HStack>
}
