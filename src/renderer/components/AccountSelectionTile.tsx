import {Button} from '@astryxdesign/core/Button'
import {HStack} from '@astryxdesign/core/HStack'
import {Icon} from '@astryxdesign/core/Icon'
import {Spinner} from '@astryxdesign/core/Spinner'
import {Text} from '@astryxdesign/core/Text'
import {VStack} from '@astryxdesign/core/VStack'
import {Check, UserRound} from 'lucide-react'
import type {Account} from '../types'
import {resolveAccountIcon} from '../accountIcons'
import {accountRegionForGame} from '../accountRegions'
import type {AccountConnection} from '../accountConnection'
import {t, useLocale} from '../i18n'
import {usePlayerPrivacy} from './PlayerPrivacy'

export function AccountSelectionTile({account, phase, isBusy, onUse, onEdit, onSelect}: {
  account: Account
  phase?: AccountConnection['phase']
  isBusy: boolean
  onUse: () => void
  onEdit: () => void
  onSelect: () => void
}) {
  useLocale()
  const {displayName, enabled: privateMode} = usePlayerPrivacy()
  const identity = displayName(account.riotId)
  const name = privateMode ? identity : account.nickname?.trim() || identity.split('#')[0]
  const artwork = resolveAccountIcon(account)
  const region = accountRegionForGame(account, 'League of Legends') ?? accountRegionForGame(account, 'VALORANT')
  return <VStack className="pd-account-tile" role="listitem" data-phase={phase ?? 'idle'} aria-label={identity}>
    <VStack className="pd-account-tile__content" align="center" gap={4} inert={Boolean(phase)}>
      <Button className="pd-account-tile__portrait" variant="ghost" label={t('Open profile for {{name}}', {name: identity})} onClick={onSelect}>
        {artwork ? <img src={artwork.image} alt="" loading="lazy" draggable={false} /> : <Icon icon={UserRound} size="lg" />}
      </Button>
      <VStack className="pd-account-tile__identity" align="center" width="100%" gap={0}>
        <Text className="pd-account-tile__name" weight="semibold" aria-hidden="true">{name}</Text>
        <HStack className="pd-account-tile__full-name" align="center" justify="center" gap={1.5} width="100%">
          <Text className="pd-account-tile__riot-id" weight="semibold">{identity}</Text>
          {region && <Text className="pd-account-tile__region" type="supporting">{region}</Text>}
        </HStack>
      </VStack>
      <VStack className="pd-account-tile__actions" gap={2} width="100%">
        <Button className="pd-account-tile__use" variant="primary" label={t('Use')} aria-label={t('Use {{name}}', {name: identity})} onClick={onUse} isDisabled={isBusy} width="100%" />
        <Button variant="secondary" label={t('Edit')} aria-label={t('Edit {{name}}', {name: identity})} onClick={onEdit} isDisabled={isBusy} width="100%" />
      </VStack>
    </VStack>
    {phase && <VStack className="pd-account-tile__status" align="center" justify="center" gap={3} role="status" aria-live="polite"
      aria-label={phase === 'pending' ? t('Waiting for Riot approval') : t('Approved by Riot')}>
      {phase === 'pending' ? <Spinner size="xl" aria-label={t('Waiting for Riot approval')} /> : <Icon className="pd-account-tile__check" icon={Check} size="lg" />}
      {phase === 'pending' && <Text weight="semibold">{t('Connecting…')}</Text>}
    </VStack>}
  </VStack>
}
