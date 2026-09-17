import {useEffect, useMemo, useState} from 'react'
import {Button} from '@astryxdesign/core/Button'
import {CommandPalette} from '@astryxdesign/core/CommandPalette'
import {HStack} from '@astryxdesign/core/HStack'
import {Icon} from '@astryxdesign/core/Icon'
import {StatusDot} from '@astryxdesign/core/StatusDot'
import {Text} from '@astryxdesign/core/Text'
import {TopNav} from '@astryxdesign/core/TopNav'
import {createStaticSource} from '@astryxdesign/core/Typeahead'
import {EyeOff, Search} from 'lucide-react'
import type {Account, AppState} from '../types'
import type {Page} from './AppNavigation'
import {usePlayerPrivacy} from './PlayerPrivacy'

const destinations: Array<{id: Page; label: string}> = [
  {id: 'overview', label: 'Accounts'}, {id: 'search', label: 'Player search'},
  {id: 'watchlist', label: 'Watchlist'}, {id: 'current', label: 'Current match'},
  {id: 'settings', label: 'Settings'},
]

export function WorkspaceBar({state, onPage, onSelect, onAdd, onLock}: {
  state: AppState
  onPage: (page: Page) => void
  onSelect: (account: Account) => void
  onAdd: () => void
  onLock: () => void
}) {
  const [open, setOpen] = useState(false)
  const {displayName, enabled} = usePlayerPrivacy()
  const source = useMemo(() => createStaticSource([
    ...destinations.map(item => ({...item, auxiliaryData: {group: 'Go to'}})),
    ...state.accounts.map(account => ({id: `account:${account.id}`, label: displayName(account.riotId), auxiliaryData: {group: 'Your accounts'}})),
    {id: 'add', label: 'Add account', auxiliaryData: {group: 'Actions'}},
    {id: 'lock', label: 'Lock Peaks', auxiliaryData: {group: 'Actions'}},
  ]), [state.accounts, displayName])

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') {
        if (!open && document.querySelector('dialog[open]')) return
        event.preventDefault()
        setOpen(previous => !previous)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open])

  const select = (id: string) => {
    setOpen(false)
    if (id === 'add') onAdd()
    else if (id === 'lock') onLock()
    else if (id.startsWith('account:')) {
      const account = state.accounts.find(item => `account:${item.id}` === id)
      if (account) onSelect(account)
    } else if (destinations.some(item => item.id === id)) onPage(id as Page)
  }

  return <>
    <TopNav className="pd-workspace-bar" label="App controls"
      heading={<Text className="pd-wordmark" weight="bold">PEAKS</Text>}
      endContent={<HStack gap={5} align="center">
        <HStack className="pd-client-indicator" gap={2} align="center"><StatusDot label={state.riotClient.detected ? 'Riot Client detected' : 'Riot Client offline'} variant={state.riotClient.detected ? 'accent' : 'neutral'} /><Text type="supporting">{state.riotClient.detected ? 'Client connected' : 'Client offline'}</Text></HStack>
        <Button className="pd-command-trigger" label="Search accounts and commands" tooltip="Quick switch · Ctrl K" variant="secondary" onClick={() => setOpen(true)}>
          <HStack gap={3} align="center"><Icon icon={Search} size="sm" /><Text color="secondary">Search…</Text><Text className="pd-key-hint" type="supporting">Ctrl K</Text></HStack>
        </Button>
        {state.settings.streamerMode ? <Icon icon={EyeOff} color="secondary" label="Streamer Mode enabled" /> : null}
      </HStack>}
    />
    <CommandPalette key={enabled ? 'private' : 'visible'} isOpen={open} onOpenChange={setOpen} searchSource={source} onValueChange={select} label="Search accounts and commands" emptySearchText="No matching accounts or commands." />
  </>
}
