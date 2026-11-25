import type {ReactNode} from 'react'
import {Clock3, UsersRound} from 'lucide-react'
import {t} from '../i18n'
import {gameProfileIcon} from '../profileAssets'
import {Heading, HStack, Icon, StatusDot, Text, Tooltip, VStack} from '../ui'
import type {Game} from '../types'
import './liveMatch.css'

export function LiveMatchHeader({game, title, mode, elapsed, playerCount, stale, score}: {
  game: Game
  title: string
  mode?: string
  elapsed?: string
  playerCount: number
  stale?: boolean
  score: ReactNode
}) {
  const status = stale ? t('Awaiting update') : t('In game')
  const count = t('{{count}} players in this session', {count: playerCount})
  const context = [game === title ? undefined : game, mode === title ? undefined : mode].filter(Boolean).join(' · ')
  return <HStack className="live-match-header" data-game={game} align="center" gap={4}>
    <HStack className="live-match-header__identity" align="center" gap={3}>
      <img src={gameProfileIcon(game)} alt="" className="live-match-header__mark" />
      <VStack gap={0.5}>
        <Heading className="live-match-header__title" level={2}>{title}</Heading>
        {context ? <Text className="live-match-header__mode" color="secondary">{context}</Text> : null}
      </VStack>
    </HStack>
    {score ? <HStack className="live-match-header__score" justify="center">{score}</HStack> : null}
    <HStack className="live-match-header__telemetry" align="center" gap={4} wrap>
      {elapsed ? <Tooltip content={t('Elapsed time')}><HStack as="span" align="center" gap={1.5}><Icon icon={Clock3} size="sm" /><Text hasTabularNumbers>{elapsed}</Text></HStack></Tooltip> : null}
      <Tooltip content={count}><HStack as="span" aria-label={count} align="center" gap={1.5}><Icon icon={UsersRound} size="sm" /><Text hasTabularNumbers>{playerCount}</Text></HStack></Tooltip>
      <HStack className="live-match-header__status" data-stale={stale || undefined} align="center" gap={1.5}>
        <StatusDot variant={stale ? 'neutral' : 'success'} label={status} />
        <Text>{status}</Text>
      </HStack>
    </HStack>
  </HStack>
}
