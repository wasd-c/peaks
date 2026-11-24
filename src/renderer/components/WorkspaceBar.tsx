import {Badge, Tooltip} from 'antd'
import riotFist from '../assets/riot-fist.png'
import {t, useLocale} from '../i18n'
import {useEffect, useMemo, useState} from 'react'
import {Avatar, AvatarStatusDot, Button, CommandPalette, HStack, Icon, Text, TopNav, createStaticSource} from '../ui'
import {EyeOff, Search} from 'lucide-react'
import type {Account, AppState} from '../types'
import type {Page} from './AppNavigation'
import {usePlayerPrivacy} from './PlayerPrivacy'
import {FavoriteGameButton} from './FavoriteGameButton'
import {resolveAccountIcon} from '../accountIcons'

/** The account Peaks follows, next to the wordmark: who is signed in, one click from their profile. */
function ActiveAccount({account, isActive, onOpen}: {account: Account; isActive: boolean; onOpen: () => void}) {
  const {displayName} = usePlayerPrivacy()
  const identity = displayName(account.riotId)
  const status = isActive ? t('Active Riot account') : t('Saved profile')
  return <Button className="pd-active-account" variant="ghost" label={t('Open profile for {{name}}', {name: identity})} tooltip={status} onClick={onOpen}>
    <HStack gap={3} align="center">
      <Avatar size="sm" shape="rounded" name={identity} src={resolveAccountIcon(account)?.image} tooltip={false}
        status={<AvatarStatusDot variant={isActive ? 'success' : 'neutral'} label={status} />} />
      <Text weight="bold" maxLines={1}>{identity}</Text>
    </HStack>
  </Button>
}

const destinations: Array<{id: Page; label: string}> = [
  {id: 'overview', label: 'Accounts'}, {id: 'search', label: 'Player search'},
  {id: 'watchlist', label: 'Watchlist'}, {id: 'current', label: 'Current match'},
  {id: 'settings', label: 'Settings'},
]

export function WorkspaceBar({state, profileAccount, onStateChange, onPage, onSelect, onAdd, onLock}: {
  state: AppState
  profileAccount?: Account
  onStateChange: (state: AppState) => void
  onPage: (page: Page) => void
  onSelect: (account: Account) => void
  onAdd: () => void
  onLock: () => void
}) {
  const language = useLocale()
  const [open, setOpen] = useState(false)
  const {displayName, enabled} = usePlayerPrivacy()
  const source = useMemo(() => createStaticSource([
    ...destinations.map(item => ({...item, label: t(item.label, {lng: language}), auxiliaryData: {group: t('Go to')}})),
    ...state.accounts.map(account => ({id: `account:${account.id}`, label: displayName(account.riotId), auxiliaryData: {group: t('Your accounts')}})),
    {id: 'add', label: t('Add account'), auxiliaryData: {group: t('Actions')}},
    {id: 'lock', label: t('Lock Peaks'), auxiliaryData: {group: t('Actions')}},
  ]), [state.accounts, displayName, language])

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
    <TopNav className="pd-workspace-bar" label={t("App controls")}
      heading={<HStack gap={4} align="center">
        <Text className="pd-wordmark" weight="bold">PEAKS</Text>
        {profileAccount ? <ActiveAccount account={profileAccount} isActive={state.activeAccountId === profileAccount.id} onOpen={() => onPage('account')} /> : null}
      </HStack>}
      endContent={<HStack gap={5} align="center">
        <Tooltip title={state.riotClient.detected ? t("Riot Client detected") : t("Riot Client offline")}>
          <Badge dot status={state.riotClient.detected ? 'success' : 'default'} offset={[-2, 22]} className="pd-client-indicator">
            <img src={riotFist} alt={state.riotClient.detected ? t("Riot Client detected") : t("Riot Client offline")} data-online={state.riotClient.detected || undefined} />
          </Badge>
        </Tooltip>
        <FavoriteGameButton state={state} onStateChange={onStateChange} />
        <Button className="pd-command-trigger" label={t("Search accounts and commands")} tooltip={t("Quick switch · Ctrl K")} variant="secondary" onClick={() => setOpen(true)}>
          <HStack gap={3} align="center"><Icon icon={Search} size="sm" /><Text color="secondary">{t("Search…")}</Text><Text className="pd-key-hint" type="supporting">{t("Ctrl K")}</Text></HStack>
        </Button>
        {state.settings.streamerMode ? <Icon icon={EyeOff} color="secondary" label={t("Streamer Mode enabled")} /> : null}
      </HStack>}
    />
    <CommandPalette key={enabled ? 'private' : 'visible'} isOpen={open} onOpenChange={setOpen} searchSource={source} onValueChange={select} label={t("Search accounts and commands")} emptySearchText={t("No matching accounts or commands.")} />
  </>
}
