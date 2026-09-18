import {useState} from 'react'
import {Button} from '@astryxdesign/core/Button'
import {EmptyState} from '@astryxdesign/core/EmptyState'
import {Grid} from '@astryxdesign/core/Grid'
import {HStack} from '@astryxdesign/core/HStack'
import {Icon} from '@astryxdesign/core/Icon'
import {SegmentedControl, SegmentedControlItem} from '@astryxdesign/core/SegmentedControl'
import {Text} from '@astryxdesign/core/Text'
import {TextInput} from '@astryxdesign/core/TextInput'
import {VStack} from '@astryxdesign/core/VStack'
import {Grid2X2, Grid3X3, Plus, Search} from 'lucide-react'
import {accountRegionLabel} from '../accountRegions'
import {displayText, t, useLocale} from '../i18n'
import type {Account, AppState} from '../types'
import {AccountSelectionTile} from '../components/AccountSelectionTile'
import type {AccountConnection} from '../accountConnection'
import {usePlayerPrivacy} from '../components/PlayerPrivacy'
import {AuthenticatedScreen, EmptyAccounts, rankLabel, strongestRank, type AuthenticatedView} from './shared'

export interface OverviewScreenProps {
  state: AppState
  view: AuthenticatedView
  onView: (view: AuthenticatedView) => void
  onSelect: (account: Account) => void
  onAdd: () => void
  onUse: (account: Account) => void
  onEdit: (account: Account) => void
  connection?: AccountConnection | null
}

export function OverviewScreen({state, view, onView, onSelect, onAdd, onUse, onEdit, connection}: OverviewScreenProps) {
  useLocale()
  const {displayName, enabled: privacyEnabled} = usePlayerPrivacy()
  const [query, setQuery] = useState('')
  const visible = state.accounts.filter(account => (
    `${displayName(account.riotId)} ${privacyEnabled ? '' : account.nickname ?? ''} ${accountRegionLabel(account)}`.toLocaleLowerCase().includes(query.trim().toLocaleLowerCase())
  ))
  const highest = strongestRank(state.accounts)
  const compact = view === 'list'

  return (
    <AuthenticatedScreen
      actions={<Button icon={<Icon icon={Plus} />} label={t('Add account')} onClick={onAdd} size="lg" />}
      screen="overview" title={t('Accounts')}>
      <VStack gap={6}>
        <HStack className="pd-account-toolbar" justify="between" align="center" gap={4} wrap="wrap">
          <HStack gap={2} align="center" wrap="wrap">
            <Text weight="semibold">{t('{{count}} accounts', {count: state.accounts.length})}</Text>
            {highest && highest.tier.toLowerCase() !== 'unranked' && <Text color="secondary">{t('· Highest rank {{rank}}', {rank: displayText(rankLabel(highest))})}</Text>}
          </HStack>
          <HStack gap={3} align="center" className="pd-account-toolbar__controls">
            <TextInput label={t('Find an account')} isLabelHidden placeholder={t('Find a name or region…')} startIcon={Search} value={query} onChange={setQuery} hasClear size="sm" />
            <SegmentedControl label={t('Account density')} value={view} onChange={value => onView(value as AuthenticatedView)} size="sm">
              <SegmentedControlItem icon={<Icon icon={Grid2X2} />} isLabelHidden label={t('Comfortable')} value="grid" />
              <SegmentedControlItem icon={<Icon icon={Grid3X3} />} isLabelHidden label={t('Compact')} value="list" />
            </SegmentedControl>
          </HStack>
        </HStack>
        {state.accounts.length === 0 ? <EmptyAccounts onAdd={onAdd} /> : visible.length === 0 ?
          <EmptyState title={t('No accounts found')} description={t('Try another name or region.')} icon={<Icon icon={Search} />} actions={<Button label={t('Clear search')} onClick={() => setQuery('')} />} /> :
          <VStack align="center" width="100%" className="pd-account-stage" data-sparse={visible.length <= 4}>
            <Grid columns={{minWidth: compact ? 166 : 218, max: compact ? 7 : 5, repeat: 'fit'}} gap={compact ? 3 : 5} width="100%"
              maxWidth={`calc(${visible.length} * ${compact ? 'var(--spacing-12) * 4' : 'var(--spacing-12) * 5.5'})`}
              className="pd-account-grid" data-density={compact ? 'compact' : 'comfortable'} role="list" aria-label={t('Your Riot accounts')}>
              {visible.map(account => <AccountSelectionTile key={account.id} account={account}
                phase={connection?.accountId === account.id ? connection.phase : undefined}
                isBusy={Boolean(connection)} onUse={() => onUse(account)} onEdit={() => onEdit(account)} onSelect={() => onSelect(account)} />)}
            </Grid>
          </VStack>
        }
      </VStack>
    </AuthenticatedScreen>
  )
}
