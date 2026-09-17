import {usePlayerPrivacy} from '../components/PlayerPrivacy'
import {useRef, useState} from 'react'
import {Button} from '@astryxdesign/core/Button'
import {EmptyState} from '@astryxdesign/core/EmptyState'
import {Heading} from '@astryxdesign/core/Heading'
import {HStack} from '@astryxdesign/core/HStack'
import {Icon} from '@astryxdesign/core/Icon'
import {List, ListItem} from '@astryxdesign/core/List'
import {Section} from '@astryxdesign/core/Section'
import {Text} from '@astryxdesign/core/Text'
import {TextInput} from '@astryxdesign/core/TextInput'
import {VStack} from '@astryxdesign/core/VStack'
import {ArrowUpRight, ChevronRight, Clock3, Search as SearchIcon} from 'lucide-react'
import {gameArtwork} from '../assets'
import {playerIsWatched} from '../playerProfiles'
import type {AppState, Player} from '../types'
import {
  AuthenticatedScreen,
  PlayerList,
  type ActionCallback,
  type InvokeCallback,
} from './shared'

export interface SearchScreenProps {
  state: AppState
  invoke: InvokeCallback
  action: ActionCallback
  onSelectPlayer: (player: Player) => void
}

export function SearchScreen({state, invoke, action, onSelectPlayer}: SearchScreenProps) {
  const {displayName, enabled} = usePlayerPrivacy()
  const [query, setQuery] = useState('')
  const searchPending = useRef(false)
  const [results, setResults] = useState<Player[]>([])
  const [isSearching, setIsSearching] = useState(false)
  const [hasSearched, setHasSearched] = useState(false)
  const [message, setMessage] = useState('')
  const visibleResults = results.map(player => ({
    ...player,
    followed: playerIsWatched(player, state.followed),
  }))

  const canSearch = query.trim().includes('#') && !isSearching

  const search = async (candidate = query) => {
    if (!candidate.trim().includes('#') || searchPending.current) return
    searchPending.current = true
    setQuery(candidate)
    setIsSearching(true)
    setMessage('')
    try {
      const players = await invoke<Player[]>('search', {query: candidate.trim()})
      setResults(players)
      setHasSearched(true)
      await action('state')
    } catch (error) {
      setResults([])
      setHasSearched(true)
      setMessage(
        String(error).includes('LOCAL_RIOT_CLIENT_UNAVAILABLE')
          ? 'Open Riot Client and sign in, then try again.'
          : 'Unable to search right now. Try again in a moment.',
      )
    } finally {
      searchPending.current = false
      setIsSearching(false)
    }
  }

  return (
    <AuthenticatedScreen
      eyebrow="PLAYERS"
      screen="search"
      title="Player search">
      <VStack className="pd-search" gap={8}>
        <Section className="pd-search-hero" padding={0} variant="transparent">
          <img className="pd-search-art" src={gameArtwork('VALORANT')} alt="" />
          <VStack className="pd-search-form" gap={6}>
            <VStack gap={3}>
              <Heading level={2} type="display-3">Find a player</Heading>
              <Text color="secondary">Enter their Riot ID to see their profile and ranks.</Text>
            </VStack>
            <VStack gap={4}>
            <HStack align="end" className="pd-search-query" gap={2}>
              <TextInput
                hasClear
                label="Riot ID"
                type={enabled ? 'password' : 'text'}
                onChange={setQuery}
                onEnter={() => { void search() }}
                placeholder="GameName#TAG"
                startIcon={SearchIcon}
                size="lg"
                value={query}
              />
              <Button
                endContent={<Icon icon={ArrowUpRight} />}
                isDisabled={!canSearch && !isSearching}
                isLoading={isSearching}
                label="Search"
                size="lg"
                onClick={() => { void search() }}
                variant="primary"
              />
            </HStack>
            </VStack>
            {message ? <Text color="secondary" display="block" role="alert">{message}</Text> : null}
          </VStack>
        </Section>

        {visibleResults.length > 0 ? (
          <PlayerList action={action} heading="Search results" onSelect={onSelectPlayer} players={visibleResults} />
        ) : null}

        {hasSearched && results.length === 0 && !message ? (
          <EmptyState
            description="Check the name and #tag, then try again."
            icon={<Icon color="secondary" icon={SearchIcon} />}
            title="No matching players"
          />
        ) : null}

        <Section className="pd-search-history" padding={0} variant="transparent">
          {state.searchHistory.length > 0 ? (
            <List
              className="peaks-dense-list"
              density="compact"
              hasDividers
              header={
                <HStack align="center" justify="between" gap={3}>
                  <Heading level={2}>Recent searches</Heading>
                </HStack>
              }>
              {state.searchHistory.map(entry => (
                <ListItem
                  endContent={<Icon color="secondary" icon={ChevronRight} />}
                  key={entry}
                  label={displayName(entry)}
                  isDisabled={isSearching}
                  onClick={() => { void search(entry) }}
                  startContent={<Icon color="secondary" icon={Clock3} />}
                />
              ))}
            </List>
          ) : (
            <HStack className="pd-search-history-empty" gap={4} align="center">
              <Icon color="secondary" icon={Clock3} size="lg" />
              <VStack gap={1}><Heading level={2}>Recent searches</Heading><Text color="secondary">Your searches will appear here.</Text></VStack>
            </HStack>
          )}
        </Section>

      </VStack>
    </AuthenticatedScreen>
  )
}
