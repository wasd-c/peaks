import {useState} from 'react'
import {Button, HStack, Icon, Table, proportional, pixel, useTableSortable, Text} from '../ui'
import {Check, LogIn, Pencil, UserRound} from 'lucide-react'
import {resolveAccountIcon} from '../accountIcons'
import type {AccountConnection} from '../accountConnection'
import {localeTags, t, useLocale} from '../i18n'
import type {Account} from '../types'
import {usePlayerPrivacy} from './PlayerPrivacy'

export function AccountTable({accounts, connection, onSelect, onUse, onEdit}: {
  accounts: Account[]
  connection?: AccountConnection | null
  onSelect: (account: Account) => void
  onUse: (account: Account) => void
  onEdit: (account: Account) => void
}) {
  const locale = useLocale()
  const {displayName, enabled: privateMode} = usePlayerPrivacy()
  const [sort, setSort] = useState<Array<{sortKey: string; direction: 'ascending' | 'descending'}>>([{sortKey: 'lastConnectedAt', direction: 'descending'}])
  const rows = accounts.map(account => {
    const identity = displayName(account.riotId)
    return {id: account.id, account, identity, name: privateMode ? identity : account.nickname?.trim() || identity.split('#')[0],
      lastConnectedAt: account.lastConnectedAt != null && Number.isFinite(account.lastConnectedAt) && account.lastConnectedAt > 0 ? account.lastConnectedAt : null}
  })
  const collator = new Intl.Collator(localeTags[locale], {numeric: true, sensitivity: 'base'})
  rows.sort((a, b) => {
    const recent = (b.lastConnectedAt ?? 0) - (a.lastConnectedAt ?? 0)
    const name = collator.compare(a.name, b.name)
    return sort[0]?.sortKey === 'name' ? name * (sort[0].direction === 'ascending' ? 1 : -1) || recent : recent || name
  })
  const sortable = useTableSortable<typeof rows[number]>({sort, onSortChange: next => {
    // Date ordering always returns to newest first; names can go both ways.
    setSort(next[0]?.sortKey === 'name' ? next : [{sortKey: 'lastConnectedAt', direction: 'descending'}])
  }})
  const date = new Intl.DateTimeFormat(localeTags[locale], {dateStyle: 'medium', timeStyle: 'short'})
  return <Table className="pd-account-table" aria-label={t('Your Riot accounts')} data={rows} idKey="id"
    density="spacious" dividers="none" hasHover plugins={{sortable}} columns={[
      {key: 'portrait', header: '', width: pixel(88), renderCell: row => {
        const artwork = resolveAccountIcon(row.account)
        return <Button className="pd-account-table__portrait" label={t('Open profile for {{name}}', {name: row.identity})} variant="ghost" onClick={() => onSelect(row.account)}>
          {artwork ? <img src={artwork.image} alt="" loading="lazy" draggable={false} /> : <Icon icon={UserRound} />}
        </Button>
      }},
      {key: 'name', header: t('Name'), width: proportional(2), sortable: true,
        renderCell: row => <Button className="pd-account-table__name" label={row.name} variant="ghost" onClick={() => onSelect(row.account)}><Text weight="bold">{row.name}</Text></Button>},
      {key: 'lastConnectedAt', header: t('Last connection date'), width: proportional(2), sortable: true,
        renderCell: row => <Text color="secondary" hasTabularNumbers>{row.lastConnectedAt == null ? t('Not recorded') : date.format(row.lastConnectedAt)}</Text>},
      {key: 'actions', header: '', width: pixel(220), align: 'end', renderCell: row => {
        const phase = connection?.accountId === row.id ? connection.phase : undefined
        return <HStack gap={2} justify="end" align="center">
          <Button label={t(phase === 'pending' ? 'Connecting…' : phase === 'approved' ? 'Approved by Riot' : 'Use')}
            aria-label={phase ? undefined : t('Use {{name}}', {name: row.identity})} size="sm" variant="secondary"
            isLoading={phase === 'pending'} icon={phase === 'approved' ? <Icon icon={Check} /> : <Icon icon={LogIn} />}
            isDisabled={Boolean(connection)} onClick={() => onUse(row.account)} />
          <Button label={t('Edit {{name}}', {name: row.identity})} tooltip={t('Edit')} icon={<Icon icon={Pencil} />} isIconOnly size="sm" variant="ghost"
            isDisabled={Boolean(connection)} onClick={() => onEdit(row.account)} />
        </HStack>
      }},
    ]} />
}
