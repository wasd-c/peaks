import {t, useLocale, displayText} from '../i18n'
import {useState, type ReactNode} from 'react'
import {Button as AntButton, Card, Flex, Tabs, Tag, Tooltip} from 'antd'
import {Button, FormLayout, HStack, Icon, List, ListItem, Selector, Switch, Text, TextInput, VStack} from '../ui'
import {Check, ClipboardCheck, Database, EyeOff, Gamepad2, Gift, KeyRound, Languages, LockKeyhole, MessageCircle, Monitor, Pencil, Rocket, Search, ShieldCheck, Sparkles} from 'lucide-react'
import type {AppState} from '../types'
import {DiscordPresenceSettings} from '../components/DiscordPresenceSettings'
import {TelemetrySettings} from '../components/TelemetrySettings'
import {LanguageSelector} from '../components/LanguageSelector'
import {ReleaseNotesDialog} from '../components/ReleaseNotesDialog'
import {passcodeErrorMessage} from '../passcodeMessages'
import {AuthenticatedScreen, type ActionCallback} from './shared'

const autoLockOptions = () => [{label: t('Only when Peaks closes'), value: '0'}, ...[1, 5, 15, 30, 60].map(minutes => ({
  label: t('{{count}} minutes', {count: minutes}),
  value: String(minutes),
}))]

export interface SettingsScreenProps {
  state: AppState
  action: ActionCallback
}

function ApiKeyControl({action}: {action: ActionCallback}) {
  useLocale()
  const [key, setKey] = useState('')
  return (
    <HStack align="end" className="pd-settings-api-control" gap={2}>
      <TextInput
        isLabelHidden
        label={t("Riot developer API key")}
        onChange={setKey}
        placeholder="RGAPI-••••••••"
        type="password"
        value={key}
      />
      <Button
        clickAction={async () => {
          await action('api_key', {key: key.trim()})
          setKey('')
        }}
        icon={<Icon icon={KeyRound} />}
        isDisabled={!key.trim()}
        label={t("Save key")}
      />
    </HStack>
  )
}

export function ChangeSecurityCode({action, startEditing = false, onDone}: {action: ActionCallback; startEditing?: boolean; onDone?: () => void}) {
  useLocale()
  const [editing, setEditingState] = useState(startEditing)
  const setEditing = (value: boolean) => { setEditingState(value); if (!value) onDone?.() }
  const [oldPin, setOldPin] = useState('')
  const [newPin, setNewPin] = useState('')
  const [confirmPin, setConfirmPin] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const clear = () => { setOldPin(''); setNewPin(''); setConfirmPin(''); setError('') }
  const valid = [oldPin, newPin, confirmPin].every(value => /^[0-9]{4}$/.test(value))
  const save = async () => {
    if (busy || !valid) return
    if (newPin !== confirmPin) { setError('The new passcodes do not match.'); return }
    if (oldPin === newPin) { setError('Choose a different passcode.'); return }
    setBusy(true)
    setError('')
    try {
      await action('change_pin', {oldPin, newPin, confirmPin}, true)
      clear()
      setEditing(false)
    } catch (failure) {
      setOldPin('')
      setError(passcodeErrorMessage(failure, 'Could not change the password. Try again.'))
    } finally {
      setBusy(false)
    }
  }
  if (!editing) return (
    <Button icon={<Icon icon={KeyRound} />} label={t("Change security code")} clickAction={() => setEditing(true)} />
  )
  return (
    <VStack gap={4}>
      <FormLayout>
        <TextInput label={t("Current security code")} type="password"
          isDisabled={busy} value={oldPin} onChange={value => { if (/^[0-9]{0,4}$/.test(value)) setOldPin(value) }} />
        <TextInput label={t("New security code")} type="password"
          description={t("Choose four digits.")} isDisabled={busy} value={newPin} onChange={value => { if (/^[0-9]{0,4}$/.test(value)) setNewPin(value) }} />
        <TextInput label={t("Confirm new security code")} type="password"
          isDisabled={busy} value={confirmPin} onChange={value => { if (/^[0-9]{0,4}$/.test(value)) setConfirmPin(value) }} onEnter={() => { void save() }} />
      </FormLayout>
      {error ? <Text role="alert">{displayText(error)}</Text> : null}
      <HStack gap={2}>
        <Button label={t("Save new code")} variant="primary" isDisabled={!valid} isLoading={busy} clickAction={save} />
        <Button label={t("Cancel")} variant="ghost" isDisabled={busy} clickAction={() => { clear(); setEditing(false) }} />
      </HStack>
    </VStack>
  )
}

export function SettingsScreen({state, action}: SettingsScreenProps) {
  useLocale()
  const [notesOpen, setNotesOpen] = useState(false)
  const [editingCode, setEditingCode] = useState(false)
  const settings = state.settings
  const section = (children: ReactNode) => <Card size="small" className="pd-settings-group" styles={{body: {padding: 4}}}>
    <List density="spacious" hasDividers>{children}</List>
  </Card>
  const on = (label: string) => <Tag icon={<Check size={12} aria-hidden />} color="default" className="pd-settings-tag">{label}</Tag>
  const tabs = [
    {key: 'privacy', icon: ShieldCheck, label: t('Privacy & security'), children: <Flex vertical gap={16}>
      {section(<>
        <ListItem startContent={<Icon icon={LockKeyhole} color="secondary" />} label={t("Automatic lock")}
          description={settings.autoLockMinutes === 0 ? t("Stay unlocked until you close Peaks. You can still lock it manually.") : undefined}
          endContent={<Selector isLabelHidden label={t("Automatic lock interval")} size="sm" options={autoLockOptions()}
            value={String(settings.autoLockMinutes)} onChange={value => { void action('settings', {autoLockMinutes: Number(value)}) }} />} />
        <ListItem startContent={<Icon icon={EyeOff} color="secondary" />} label={t("Streamer Mode")}
          description={t("Replace everyone’s names with Player 1, Player 2, and so on throughout Peaks.")}
          endContent={<Switch label={t("Streamer Mode")} isLabelHidden size="sm" value={Boolean(settings.streamerMode)}
            changeAction={value => action('settings', {streamerMode: value}, true)} />} />
        <ListItem startContent={<Icon icon={ClipboardCheck} color="secondary" />} label={t("Clipboard safety")}
          description={t('Copied authentication codes clear after {{count}} seconds.', {count: settings.clipboardClearSeconds})}
          endContent={on(t("Always on"))} />
        <ListItem startContent={<Icon icon={KeyRound} color="secondary" />} label={t("Security code")}
          endContent={editingCode ? null : <Tooltip title={t("Change security code")}><AntButton icon={<Pencil size={14} />} aria-label={t("Change security code")} onClick={() => setEditingCode(true)} /></Tooltip>} />
        <TelemetrySettings />
      </>)}
      {editingCode ? <Card size="small" title={t("Security code")}><ChangeSecurityCode action={action} startEditing onDone={() => setEditingCode(false)} /></Card> : null}
    </Flex>},
    {key: 'appearance', icon: Monitor, label: t('Appearance'), children: section(<>
      <ListItem startContent={<Icon icon={Languages} color="secondary" />} label={t('Language')} endContent={<LanguageSelector isLabelHidden />} />
      <ListItem startContent={<Icon icon={Sparkles} color="secondary" />} label={t("Reduce motion")} description={t("Limit animations and ambient effects.")}
        endContent={<Switch label={t("Reduce motion")} isLabelHidden size="sm" value={settings.reduceMotion}
          changeAction={value => action('settings', {reduceMotion: value})} />} />
    </>)},
    {key: 'games', icon: Gamepad2, label: t('Games'), children: section(
      <ListItem startContent={<Icon icon={Rocket} color="secondary" />} label={t('Game launch on sign-in')}
        description={t('Favorite game: {{game}}', {game: settings.favoriteGame ?? 'VALORANT'})}
        endContent={<Selector label={t('Game launch on sign-in')} isLabelHidden size="sm"
          value={settings.gameLaunchMode ?? (settings.autoLaunchFavoriteGame ? 'favorite' : 'off')}
          onChange={value => { void action('settings', {gameLaunchMode: value}, true) }}
          options={[
            {value: 'favorite', label: t('Favorite game')},
            {value: 'ask', label: t('Ask every time')},
            {value: 'off', label: t('No game')},
          ]} />} />,
    )},
    {key: 'data', icon: Database, label: t('Riot data'), children: <Flex vertical gap={16}>
      {section(<>
        <ListItem startContent={<Icon icon={Search} color="secondary" />} label={t("Player search")} description={t("Use your signed-in Riot client.")}
          endContent={on(t("No key required"))} />
        <ListItem startContent={<Icon icon={KeyRound} color="secondary" />} label={t("Developer API key")}
          description={t("Add an optional key for more League and TFT statistics.")}
          endContent={settings.riotApiConfigured ? on(t("Configured")) : <Tag className="pd-settings-tag">{t("Optional")}</Tag>} />
      </>)}
      <Card size="small"><ApiKeyControl action={action} /></Card>
    </Flex>},
    {key: 'discord', icon: MessageCircle, label: 'Discord', children: <DiscordPresenceSettings />},
  ]
  return (
    <AuthenticatedScreen screen="settings" title={t("Settings")}
      actions={<Tooltip title={t('What’s new in Peaks')}><AntButton type="text" icon={<Gift size={18} />} aria-label={t('What’s new in Peaks')} onClick={() => setNotesOpen(true)} /></Tooltip>}>
      <Tabs className="pd-settings-tabs" tabPlacement="start" aria-label={t("Preference sections")}
        items={tabs.map(({key, icon: Glyph, label, children}) => ({key, forceRender: true, label, icon: <Glyph size={16} aria-hidden />, children}))} />
      <ReleaseNotesDialog isOpen={notesOpen} onClose={() => setNotesOpen(false)} />
    </AuthenticatedScreen>
  )
}
