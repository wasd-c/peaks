import {useState} from 'react'
import {Alert, Badge, Button, Empty, Flex, Input, Result, Segmented, Tooltip, Typography} from 'antd'
import {Grid2X2, Plus, Search, Table2, UserPlus} from 'lucide-react'
import {accountRegionLabel} from '../accountRegions'
import {t, useLocale} from '../i18n'
import type {Account, AppState} from '../types'
import {AccountSelectionTile} from '../components/AccountSelectionTile'
import {AccountTable} from '../components/AccountTable'
import type {AccountConnection} from '../accountConnection'
import {usePlayerPrivacy} from '../components/PlayerPrivacy'
import {Grid} from '../ui'
import {AuthenticatedScreen, type AuthenticatedView} from './shared'

export interface OverviewScreenProps {
  state: AppState
  view: AuthenticatedView
  onView: (view: AuthenticatedView) => void
  onSelect: (account: Account) => void
  onAdd: () => void
  onUse: (account: Account) => void
  onCancel?: () => void
  onEdit: (account: Account) => void
  connection?: AccountConnection | null
}

export function OverviewScreen({state, view, onView, onSelect, onAdd, onUse, onCancel, onEdit, connection}: OverviewScreenProps) {
  useLocale()
  const {displayName, enabled: privacyEnabled} = usePlayerPrivacy()
  const [query, setQuery] = useState('')
  const visible = state.accounts.filter(account => (
    `${displayName(account.riotId)} ${privacyEnabled ? '' : account.nickname ?? ''} ${accountRegionLabel(account)}`.toLocaleLowerCase().includes(query.trim().toLocaleLowerCase())
  ))
  const hasAccounts = state.accounts.length > 0

  return (
    <AuthenticatedScreen screen="overview" title={t('Accounts')}
      heading={<Flex gap={12} align="center">
        <Typography.Title level={3} className="peaks-screen__title">{t('Accounts')}</Typography.Title>
        {hasAccounts ? <Badge count={state.accounts.length} color="var(--color-background-muted)" style={{color: 'var(--color-text-secondary)', boxShadow: 'none'}} /> : null}
      </Flex>}
      actions={<>
        {hasAccounts ? <Input allowClear prefix={<Search size={14} aria-hidden />} placeholder={t('Find a name or region…')} aria-label={t('Find an account')}
          value={query} onChange={event => setQuery(event.target.value)} style={{width: 240}} /> : null}
        {hasAccounts ? <Segmented value={view} onChange={value => onView(value as AuthenticatedView)} aria-label={t('Account view')} options={[
          {value: 'grid', icon: <Grid2X2 size={16} aria-hidden />, title: t('Grid view')},
          {value: 'list', icon: <Table2 size={16} aria-hidden />, title: t('Table view')},
        ]} /> : null}
        <Tooltip title={t('Add account')}><Button type="primary" icon={<Plus size={18} />} aria-label={t('Add account')} onClick={onAdd} /></Tooltip>
      </>}>
      <Flex vertical gap={16}>
        {connection?.phase === 'pending' && onCancel ? <Alert type="info" showIcon role="status" title={t('Connecting…')}
          action={<Button size="small" onClick={onCancel}>{t('Cancel')}</Button>} /> : null}
        {!hasAccounts ? <Result icon={<UserPlus size={48} aria-hidden />} title={t('No accounts yet')}
          extra={<Button type="primary" icon={<Plus size={16} />} onClick={onAdd}>{t('Add your first account')}</Button>} />
          : visible.length === 0 ? <Empty image={<Search size={40} aria-hidden />} description={t('No accounts found')}>
            <Button onClick={() => setQuery('')}>{t('Clear search')}</Button>
          </Empty>
          : view === 'list' ? <AccountTable accounts={visible} connection={connection} onSelect={onSelect} onUse={onUse} onEdit={onEdit} />
          : <Flex vertical align="center" className="pd-account-stage" data-sparse={visible.length <= 4}>
            <Grid columns={{minWidth: 218, max: 5, repeat: 'fit'}} gap={5} width="100%"
              maxWidth={`calc(${visible.length} * var(--spacing-12) * 5.5)`}
              className="pd-account-grid" role="list" aria-label={t('Your Riot accounts')}>
              {visible.map(account => <AccountSelectionTile key={account.id} account={account}
                phase={connection?.accountId === account.id ? connection.phase : undefined}
                isBusy={Boolean(connection)} onUse={() => onUse(account)} onEdit={() => onEdit(account)} onSelect={() => onSelect(account)} />)}
            </Grid>
          </Flex>}
      </Flex>
    </AuthenticatedScreen>
  )
}
