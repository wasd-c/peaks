import {t, useLocale} from '../i18n'
import {useEffect, useState} from 'react'
import {Badge, Dropdown, Flex, Menu, Tooltip} from 'antd'
import {ChevronUp, Crosshair, Fingerprint, LockKeyhole, LogOut, PanelLeft, PencilLine, Search, Settings2, UsersRound} from 'lucide-react'
import {Avatar, AvatarStatusDot, Button, Icon, Text, type IconType} from '../ui'
import type {Account, AppState} from '../types'
import {SidebarUpdate} from './SidebarUpdate'
import {usePlayerPrivacy} from './PlayerPrivacy'
import {resolveAccountIcon} from '../accountIcons'

export type Page = 'account' | 'overview' | 'search' | 'watchlist' | 'current' | 'settings'
interface AppNavigationProps {
  page: Page
  state: AppState
  onPage: (page: Page) => void
  onLock: () => void
  onEditAccount: (account: Account) => void
  onSignOutAccount: (account: Account) => void
  profileAccount?: Account
  isCollapsed: boolean
  onCollapsedChange: (isCollapsed: boolean) => void
}

type Destination = {key: Page; label: string; icon: IconType}

const COLLAPSE_KEY = 'peaks.sidebarCollapsed'

/** Sidebar open/closed, remembered between launches and toggled with Ctrl+B. */
export function useSidebarCollapsed(): [boolean, (isCollapsed: boolean) => void] {
  const [isCollapsed, setCollapsed] = useState(() => {
    try { return window.localStorage.getItem(COLLAPSE_KEY) === '1' } catch { return false }
  })
  const update = (next: boolean) => {
    setCollapsed(next)
    try { window.localStorage.setItem(COLLAPSE_KEY, next ? '1' : '0') } catch { /* storage unavailable */ }
  }
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && !event.shiftKey && !event.altKey && event.key.toLowerCase() === 'b') {
        if (document.querySelector('dialog[open]')) return
        event.preventDefault()
        setCollapsed(previous => {
          try { window.localStorage.setItem(COLLAPSE_KEY, previous ? '0' : '1') } catch { /* storage unavailable */ }
          return !previous
        })
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])
  return [isCollapsed, update]
}

/** The followed account, pinned under the navigation: profile on click, account actions behind the chevron. */
function SidebarAccount({account, isActive, isCollapsed, onOpen, onEdit, onSignOut, onLock}: {
  account: Account
  isActive: boolean
  isCollapsed: boolean
  onOpen: () => void
  onEdit: () => void
  onSignOut: () => void
  onLock: () => void
}) {
  const {displayName} = usePlayerPrivacy()
  const [menuOpen, setMenuOpen] = useState(false)
  const identity = displayName(account.riotId)
  const status = isActive ? t('Online') : t('Offline')
  const avatar = <Avatar size="sm" shape="rounded" name={identity} src={resolveAccountIcon(account)?.image} tooltip={false}
    status={<AvatarStatusDot variant={isActive ? 'success' : 'neutral'} label={status} />} />
  const menu = {
    items: [
      {key: 'edit', icon: <Icon icon={PencilLine} size="sm" />, label: t('Edit account'), onClick: onEdit},
      ...(isActive ? [{key: 'sign-out', icon: <Icon icon={LogOut} size="sm" />, label: t('Sign out of Riot'), onClick: onSignOut}] : []),
      {key: 'lock', icon: <Icon icon={LockKeyhole} size="sm" />, label: t('Lock Peaks'), onClick: onLock},
    ],
  }
  const openLabel = t('Open profile for {{name}}', {name: identity})

  if (isCollapsed) {
    return <Dropdown menu={menu} trigger={['contextMenu']}>
      <Tooltip title={identity} placement="right">
        <button type="button" className="pd-sidebar-account pd-sidebar-account--collapsed" aria-label={openLabel} onClick={onOpen}>{avatar}</button>
      </Tooltip>
    </Dropdown>
  }

  return <div className="pd-sidebar-account" data-open={menuOpen || undefined}>
    <button type="button" className="pd-sidebar-account__main" aria-label={openLabel} onClick={onOpen}>
      {avatar}
      <span className="pd-sidebar-account__text">
        <Text type="supporting" size="2xs" color="secondary" maxLines={1}>{status}</Text>
        <Text weight="bold" maxLines={1}>{identity}</Text>
      </span>
    </button>
    <Dropdown menu={menu} trigger={['click']} placement="topRight" open={menuOpen} onOpenChange={setMenuOpen}>
      <button type="button" className="pd-sidebar-account__menu" aria-label={t('Account options')} aria-haspopup="menu" aria-expanded={menuOpen}>
        <Icon icon={ChevronUp} size="sm" />
      </button>
    </Dropdown>
  </div>
}

export function AppNavigation({page, state, onPage, onLock, onEditAccount, onSignOutAccount, profileAccount, isCollapsed, onCollapsedChange}: AppNavigationProps) {
  useLocale()
  const destinations: Destination[] = [
    {key: 'overview', label: t('Accounts'), icon: Fingerprint},
    {key: 'search', label: t('Player search'), icon: Search},
    {key: 'watchlist', label: t('Watchlist'), icon: UsersRound},
    {key: 'current', label: t('Current match'), icon: Crosshair},
  ]
  const item = ({key, label, icon}: Destination) => {
    const glyph = <Icon icon={icon} size="lg" />
    return {
      key, 'aria-label': label, title: isCollapsed ? label : undefined,
      icon: key === 'current' && state.gameDetected ? <Badge dot status="error" offset={[-1, 2]}>{glyph}</Badge> : glyph,
      label,
    }
  }
  const menu = (items: Destination[]) => <Menu className="pd-navigation__menu" mode="inline" inlineCollapsed={isCollapsed} inlineIndent={0}
    selectable selectedKeys={[page]} onClick={({key}) => onPage(key as Page)} items={items.map(item)} />
  const toggleLabel = isCollapsed ? t('Show sidebar') : t('Hide sidebar')
  return (
    <Flex vertical gap={8} className="pd-navigation" data-collapsed={isCollapsed || undefined} component="nav" aria-label={t('Main navigation')}>
      <Flex align="center" justify={isCollapsed ? 'center' : 'space-between'} className="pd-navigation__header">
        {isCollapsed ? null : <button type="button" className="pd-navigation__wordmark" onClick={() => onPage('overview')} aria-label={t('Peaks · Accounts')}>PEAKS</button>}
        <Button label={toggleLabel} tooltip={`${toggleLabel} · Ctrl B`} icon={<Icon icon={PanelLeft} />} isIconOnly variant="ghost"
          aria-expanded={!isCollapsed} onClick={() => onCollapsedChange(!isCollapsed)} />
      </Flex>
      {menu(destinations)}
      <Flex vertical gap={8} className="pd-navigation__footer">
        <SidebarUpdate />
        {menu([{key: 'settings', label: t('Settings'), icon: Settings2}])}
        {profileAccount
          ? <SidebarAccount account={profileAccount} isActive={state.activeAccountId === profileAccount.id} isCollapsed={isCollapsed}
              onOpen={() => onPage('account')} onEdit={() => onEditAccount(profileAccount)} onSignOut={() => onSignOutAccount(profileAccount)} onLock={onLock} />
          : <Button className="pd-navigation__lock" label={t('Lock Peaks')} icon={<Icon icon={LockKeyhole} size="lg" />} isIconOnly variant="ghost" onClick={onLock} />}
      </Flex>
    </Flex>
  )
}
