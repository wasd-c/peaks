import {t, useLocale, displayText} from '../i18n'
import {usePlayerPrivacy} from '../components/PlayerPrivacy'
import {useRef, useState} from 'react'
import {Button, EmptyState, HStack, Icon, List, ListItem, Text, TextInput} from '../ui'
import {Card, Flex} from 'antd'
import {ArrowRight, ChevronRight, Clock3, Search as SearchIcon} from 'lucide-react'
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
  useLocale()
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
    <AuthenticatedScreen screen="search" title={t("Player search")}>
      <Flex vertical gap={16} className="pd-search">
        <Card className="pd-search-card">
          <Flex vertical gap={8}>
            <HStack align="end" className="pd-search-query" gap={2}>
              <TextInput
                hasClear
                hasAutoFocus
                isLabelHidden
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
                icon={<Icon icon={ArrowRight} />}
                isIconOnly
                isDisabled={!canSearch && !isSearching}
                isLoading={isSearching}
                label={t("Search")}
                size="lg"
                onClick={() => { void search() }}
                variant="primary"
              />
            </HStack>
            {message ? <Text color="error" display="block" role="alert">{displayText(message)}</Text> : null}
          </Flex>
        </Card>

        {visibleResults.length > 0 ? (
          <PlayerList action={action} heading={t("Search results")} onSelect={onSelectPlayer} players={visibleResults} />
        ) : null}

        {hasSearched && results.length === 0 && !message ? (
          <EmptyState icon={<SearchIcon size={40} aria-hidden />} title={t("No matching players")} />
        ) : null}

        {state.searchHistory.length > 0 ? (
          <Card size="small" title={<Flex gap={8} align="center"><Clock3 size={16} aria-hidden />{t("Recent searches")}</Flex>} styles={{body: {padding: 4}}}>
            <List className="peaks-dense-list pd-search-history" density="compact">
              {state.searchHistory.map(entry => (
                <ListItem
                  endContent={<Icon color="secondary" icon={ChevronRight} />}
                  key={entry}
                  label={displayName(entry)}
                  isDisabled={isSearching}
                  onClick={() => { void search(entry) }}
                />
              ))}
            </List>
          </Card>
        ) : null}
      </Flex>
    </AuthenticatedScreen>
  )
}
