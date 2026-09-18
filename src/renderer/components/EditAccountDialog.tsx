import {useEffect, useId, useRef, useState} from 'react'
import {Avatar} from '@astryxdesign/core/Avatar'
import {Button} from '@astryxdesign/core/Button'
import {Dialog, DialogHeader} from '@astryxdesign/core/Dialog'
import {Grid} from '@astryxdesign/core/Grid'
import {HStack} from '@astryxdesign/core/HStack'
import {Icon} from '@astryxdesign/core/Icon'
import {Layout, LayoutContent, LayoutFooter} from '@astryxdesign/core/Layout'
import {Text} from '@astryxdesign/core/Text'
import {TextInput} from '@astryxdesign/core/TextInput'
import {VStack} from '@astryxdesign/core/VStack'
import {RotateCcw, Trash2} from 'lucide-react'
import {accountGameIcon, accountIconOptions, findAccountIcon, resolveAccountIcon, type AccountIconGame} from '../accountIcons'
import {t, useLocale} from '../i18n'
import type {Account, AccountIconSelection} from '../types'
import {usePlayerPrivacy} from './PlayerPrivacy'

export interface EditAccountDialogProps {
  account: Account
  onClose: () => void
  onSave: (changes: {icon: AccountIconSelection | null; nickname: string}) => Promise<void>
  onDelete: () => Promise<void>
}

const searchable = (value: string) => value.normalize('NFKD').replace(/[\u0300-\u036f]/g, '').toLowerCase()
const games: AccountIconGame[] = ['League of Legends', 'VALORANT']

export function AccountIconPicker({selection, initialGame, onSelect, onClose}: {
  selection: AccountIconSelection | null
  initialGame: AccountIconGame
  onSelect: (icon: AccountIconSelection | null) => void
  onClose: () => void
}) {
  const language = useLocale()
  const [game, setGame] = useState(initialGame)
  const [search, setSearch] = useState('')
  const panelId = useId()
  const selected = findAccountIcon(selection)
  const query = searchable(search.trim())
  const characters = accountIconOptions(game).filter(option => !query
    || [option.name, option.characterId, ...Object.values(option.names ?? {})]
      .some(value => searchable(value).includes(query)))

  return <Dialog className="pd-dialog pd-account-picker" isOpen purpose="info"
    onOpenChange={open => { if (!open) onClose() }} padding={0}
    width="calc(var(--spacing-12) * 10)" maxHeight="calc(100dvh - var(--spacing-8))">
    <Layout height="auto" padding={4}
      header={<DialogHeader title={t('Choose an icon')} onOpenChange={open => { if (!open) onClose() }} />}
      content={<LayoutContent padding={4} isScrollable>
        <HStack gap={3} align="start">
          <VStack className="pd-account-picker__games" gap={2} as="nav" aria-label={t('Choose an icon')}>
            {games.map(value => <Button key={value} className="pd-account-picker__game-button"
              label={value} isIconOnly variant="ghost" aria-pressed={game === value} aria-controls={panelId}
              icon={<img className={`pd-account-picker__game${value === 'League of Legends' ? ' pd-account-picker__game--league' : ''}`}
                src={accountGameIcon(value)} alt="" />}
              onClick={() => { setGame(value); setSearch('') }} />)}
          </VStack>
          <VStack className="pd-account-picker__content" gap={3} minHeight={0} width="100%">
            <TextInput label={t('Search characters')} isLabelHidden placeholder={t('Search characters')}
              startIcon="search" value={search} onChange={setSearch} hasClear />
            <VStack className="pd-account-picker__roster" id={panelId} role="region"
              aria-label={game} minHeight={0} key={game}>
              {characters.length ? <Grid columns={4} gap={2}>
                {characters.map(option => {
                  const active = selected?.game === option.game && selected.characterId === option.characterId
                  const label = option.names?.[language] ?? option.name
                  return <Button key={option.characterId} label={label} className="pd-account-picker__character"
                    variant="ghost" aria-pressed={active} onClick={() => onSelect({game: option.game, characterId: option.characterId})}>
                    <VStack gap={1} align="center">
                      <img src={option.image} alt="" loading="lazy" decoding="async" />
                      <Text type="supporting">{label}</Text>
                    </VStack>
                  </Button>
                })}
              </Grid> : <VStack padding={6} align="center"><Text color="secondary" role="status">{t('No characters found')}</Text></VStack>}
            </VStack>
          </VStack>
        </HStack>
      </LayoutContent>}
      footer={<LayoutFooter padding={4}>
        <Button label={t('Use latest character')} variant="ghost" size="sm" icon={<Icon icon={RotateCcw} />}
          aria-pressed={selection === null} onClick={() => onSelect(null)} />
      </LayoutFooter>} />
  </Dialog>
}

/** Account-keyed state prevents a saved draft leaking into another account. */
export function EditAccountDialog(props: EditAccountDialogProps) {
  return <AccountEditor key={props.account.id} {...props} />
}

function AccountEditor({account, onClose, onSave, onDelete}: EditAccountDialogProps) {
  useLocale()
  const {displayName, enabled: privateMode} = usePlayerPrivacy()
  const name = displayName(account.riotId)
  const [draft, setDraft] = useState<AccountIconSelection | null>(account.accountIcon ?? null)
  const [nickname, setNickname] = useState(account.nickname ?? '')
  const [pickerOpen, setPickerOpen] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [pending, setPending] = useState<'save' | 'delete' | null>(null)
  const busy = useRef(false)
  const cancelRef = useRef<HTMLButtonElement>(null)
  const avatarRef = useRef<HTMLButtonElement>(null)
  const preview = draft ? findAccountIcon(draft) : resolveAccountIcon({...account, accountIcon: undefined})

  useEffect(() => {
    if (confirmDelete) cancelRef.current?.focus()
  }, [confirmDelete])

  const close = () => { if (!busy.current) onClose() }
  const closePicker = () => {
    setPickerOpen(false)
    requestAnimationFrame(() => avatarRef.current?.focus())
  }
  const apply = async (action: 'save' | 'delete') => {
    if (busy.current) return
    busy.current = true
    setPending(action)
    try {
      if (action === 'save') await onSave({icon: draft, nickname: nickname.trim()})
      else await onDelete()
      onClose()
    } catch {
      // The owner presents the localized error toast; preserve this draft for retry.
    } finally {
      busy.current = false
      setPending(null)
    }
  }

  return <>
    <Dialog className="pd-dialog pd-account-editor" isOpen={!pickerOpen}
      onOpenChange={open => { if (!open && !pickerOpen) close() }} purpose={pending ? 'required' : 'form'} padding={0}
      width="calc(var(--spacing-12) * 8)" maxHeight="calc(100dvh - var(--spacing-8))">
      <Layout height="auto" padding={5}
        header={<DialogHeader title={t(confirmDelete ? 'Delete account?' : 'Edit account')}
          onOpenChange={pending ? undefined : open => { if (!open) close() }} />}
        content={<LayoutContent padding={5} isScrollable>
          {confirmDelete ? <VStack gap={4} paddingBlock={3}>
            <Text weight="semibold">{name}</Text>
            <Text color="secondary">{t('This removes the account from Peaks. Your Riot account will not be deleted.')}</Text>
          </VStack> : <VStack gap={5}>
            <VStack gap={3} align="center">
              <Button ref={avatarRef} className="pd-account-editor__avatar" variant="ghost" label={t('Choose an icon')}
                isDisabled={Boolean(pending)} onClick={() => setPickerOpen(true)}>
                <Avatar name={name} src={preview?.image} size="xl" shape="rounded" tooltip={false} />
              </Button>
              <Text className="pd-account-editor__identity" weight="semibold">{name}</Text>
            </VStack>
            {!privateMode && <TextInput label={t('Nickname')} isOptional value={nickname} autoComplete="off"
              placeholder={name.split('#')[0]} onChange={setNickname} hasClear isDisabled={Boolean(pending)}
              onEnter={() => void apply('save')} />}
          </VStack>}
        </LayoutContent>}
        footer={<LayoutFooter padding={5}>
          {confirmDelete ? <VStack gap={2}>
            <Button label={t('Delete account')} variant="destructive" width="100%" icon={<Icon icon={Trash2} />}
              isDisabled={Boolean(pending)} isLoading={pending === 'delete'} onClick={() => void apply('delete')} />
            <Button ref={cancelRef} label={t('Cancel')} variant="secondary" width="100%" isDisabled={Boolean(pending)}
              onClick={() => setConfirmDelete(false)} />
          </VStack> : <VStack gap={2}>
            <Button label={t('Save')} variant="primary" width="100%" isDisabled={Boolean(pending)}
              isLoading={pending === 'save'} onClick={() => void apply('save')} />
            <Button label={t('Delete account')} variant="ghost" width="100%" isDisabled={Boolean(pending)}
              onClick={() => setConfirmDelete(true)} />
          </VStack>}
        </LayoutFooter>} />
    </Dialog>
    {pickerOpen && <AccountIconPicker selection={draft} initialGame={preview?.game ?? 'VALORANT'}
      onClose={closePicker} onSelect={icon => { setDraft(icon); closePicker() }} />}
  </>
}
