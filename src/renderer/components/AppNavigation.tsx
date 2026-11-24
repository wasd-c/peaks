import {t, useLocale} from '../i18n'
import {Badge, Flex, Menu, Tooltip} from 'antd'
import {Crosshair, Fingerprint, LockKeyhole, Mountain, Search, Settings2, UserRound, UsersRound} from 'lucide-react'
import {Button, Icon, type IconType} from '../ui'
import type {AppState} from '../types'
import {SidebarUpdate} from './SidebarUpdate'

export type Page = 'account' | 'overview' | 'search' | 'watchlist' | 'current' | 'settings'
interface AppNavigationProps {
  page: Page
  state: AppState
  onPage: (page: Page) => void
  onLock: () => void
  hasAccount?: boolean
}

type Destination = {key: Page; label: string; icon: IconType}

export function AppNavigation({page, state, onPage, onLock, hasAccount}: AppNavigationProps) {
  useLocale()
  const destinations: Destination[] = [
    ...(hasAccount ? [{key: 'account' as const, label: t('Account'), icon: UserRound}] : []),
    {key: 'overview', label: t('Accounts'), icon: Fingerprint},
    {key: 'search', label: t('Player search'), icon: Search},
    {key: 'watchlist', label: t('Watchlist'), icon: UsersRound},
    {key: 'current', label: t('Current match'), icon: Crosshair},
  ]
  const item = ({key, label, icon}: Destination) => {
    const glyph = <Icon icon={icon} size="lg" />
    return {
      key, 'aria-label': label,
      label: <Tooltip title={label} placement="right"><span className="pd-navigation__icon">
        {key === 'current' && state.gameDetected ? <Badge dot status="error" offset={[-1, 2]}>{glyph}</Badge> : glyph}
      </span></Tooltip>,
    }
  }
  const menu = (items: Destination[]) => <Menu className="pd-navigation__menu" mode="vertical" selectable selectedKeys={[page]}
    onClick={({key}) => onPage(key as Page)} items={items.map(item)} />
  return (
    <Flex vertical align="center" gap={8} className="pd-navigation" component="nav" aria-label={t('Main navigation')}>
      <Button className="pd-navigation__brand" label={t('Peaks · Accounts')} icon={<Icon icon={Mountain} size="lg" />} isIconOnly variant="ghost" onClick={() => onPage('overview')} />
      {menu(destinations)}
      <Flex vertical align="center" gap={8} className="pd-navigation__footer">
        <SidebarUpdate />
        {menu([{key: 'settings', label: t('Settings'), icon: Settings2}])}
        <Button label={t('Lock Peaks')} icon={<Icon icon={LockKeyhole} size="lg" />} isIconOnly variant="ghost" onClick={onLock} />
      </Flex>
    </Flex>
  )
}
