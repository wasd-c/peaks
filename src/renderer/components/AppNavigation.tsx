import {t, useLocale} from '../i18n'
import {Button} from '@astryxdesign/core/Button'
import {Center} from '@astryxdesign/core/Center'
import {Icon} from '@astryxdesign/core/Icon'
import {SideNav, SideNavItem, SideNavSection} from '@astryxdesign/core/SideNav'
import {VStack} from '@astryxdesign/core/VStack'
import {Crosshair, Fingerprint, LockKeyhole, Mountain, Search, Settings2, UsersRound} from 'lucide-react'
import type {AppState} from '../types'
import {SidebarUpdate} from './SidebarUpdate'

export type Page = 'overview' | 'search' | 'watchlist' | 'current' | 'settings'
interface AppNavigationProps {
  page: Page
  state: AppState
  onPage: (page: Page) => void
  onLock: () => void
}
export function AppNavigation({page, state, onPage, onLock}: AppNavigationProps) {
  useLocale()
  return (
    <SideNav className="pd-navigation" aria-label={t("Main navigation")}
      collapsible={{isCollapsed: true, hasButton: false}}
      header={<Button className="pd-navigation__brand" label={t("Peaks · Accounts")} icon={<Icon icon={Mountain} size="lg" />} isIconOnly variant="ghost" onClick={() => onPage('overview')} />}
      footer={<VStack gap={3} align="center" paddingBlock={4}>
        <SidebarUpdate />
        <Center width="var(--spacing-12)">
          <SideNavItem label={t("Settings")} icon={Settings2} isSelected={page === 'settings'} onClick={() => onPage('settings')} />
        </Center>
        <Button label={t("Lock Peaks")} tooltip={t("Lock Peaks")} icon={<Icon icon={LockKeyhole} />} isIconOnly variant="ghost" onClick={onLock} />
      </VStack>}>
      <SideNavSection title={t("Accounts and players")} isHeaderHidden>
        <SideNavItem label={t("Accounts")} icon={Fingerprint} isSelected={page === 'overview'} onClick={() => onPage('overview')} />
        <SideNavItem label={t("Player search")} icon={Search} isSelected={page === 'search'} onClick={() => onPage('search')} />
        <SideNavItem label={t("Watchlist")} icon={UsersRound} isSelected={page === 'watchlist'} onClick={() => onPage('watchlist')} />
      </SideNavSection>
      <SideNavSection title={t("Play")} isHeaderHidden>
        <SideNavItem className={state.gameDetected ? 'pd-navigation__live' : undefined} label={t("Current match")} icon={Crosshair} isSelected={page === 'current'} onClick={() => onPage('current')} />
      </SideNavSection>
    </SideNav>
  )
}
