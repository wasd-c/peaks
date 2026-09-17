import {useState} from 'react'
import {Button} from '@astryxdesign/core/Button'
import {EmptyState} from '@astryxdesign/core/EmptyState'
import {HStack} from '@astryxdesign/core/HStack'
import {Icon} from '@astryxdesign/core/Icon'
import {Text} from '@astryxdesign/core/Text'
import {TextInput} from '@astryxdesign/core/TextInput'
import {VStack} from '@astryxdesign/core/VStack'
import {Search, Star, UsersRound} from 'lucide-react'
import {usePlayerPrivacy} from '../components/PlayerPrivacy'
import type {AppState, Player} from '../types'
import {AuthenticatedScreen, PlayerList, type ActionCallback} from './shared'

export interface WatchlistScreenProps {
  state: AppState
  action: ActionCallback
  onSelectPlayer: (player: Player) => void
}

export function WatchlistScreen({state, action, onSelectPlayer}: WatchlistScreenProps) {
  const {displayName} = usePlayerPrivacy()
  const [query, setQuery] = useState('')
  const players = state.followed.filter(player => (
    displayName(player.riotId).toLocaleLowerCase().includes(query.trim().toLocaleLowerCase())
  ))
  return (
    <AuthenticatedScreen
      screen="watchlist"
      title="Watchlist">
      <VStack className="pd-watch" gap={6}>
      <HStack className="pd-watch-summary" gap={6} align="center" justify="between">
        <HStack align="center" gap={4}>
          <Icon icon={UsersRound} size="lg" />
          <VStack gap={1}><Text className="pd-watch-count" weight="semibold">{state.followed.length}</Text><Text color="secondary" type="supporting">Watched players</Text></VStack>
        </HStack>
      </HStack>
      {state.followed.length > 0 ? (
        <VStack gap={5}>
          <HStack className="pd-watch-toolbar" align="end" gap={3}>
            <TextInput label="Filter watched players" isLabelHidden placeholder="Find a watched player" startIcon={Search} hasClear value={query} onChange={setQuery} />
          </HStack>
          {players.length ? (
        <PlayerList
          action={action}
          heading={`${players.length} watched player${players.length === 1 ? '' : 's'}`}
          onSelect={onSelectPlayer}
          players={players.map(player => ({...player, followed: true}))}
        />
          ) : <EmptyState title="No players found" description="Try another name." icon={<Icon icon={Search} />} actions={<Button label="Clear search" onClick={() => setQuery('')} />} />}
        </VStack>
      ) : (
        <EmptyState
          description="Find a player in Search, then select Watch to add them here."
          icon={<Icon color="secondary" icon={Star} />}
          title="No watched players yet"
        />
      )}
      </VStack>
    </AuthenticatedScreen>
  )
}

/** Compatibility export while callers migrate to WatchlistScreen. */
export const FollowedScreen = WatchlistScreen
export type FollowedScreenProps = WatchlistScreenProps
