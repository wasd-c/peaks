import {t, useLocale, displayText} from '../i18n'
import {useState} from 'react'
import {Button} from '@astryxdesign/core/Button'
import {FormLayout} from '@astryxdesign/core/FormLayout'
import {Heading} from '@astryxdesign/core/Heading'
import {HStack} from '@astryxdesign/core/HStack'
import {Icon} from '@astryxdesign/core/Icon'
import {List, ListItem} from '@astryxdesign/core/List'
import {Section} from '@astryxdesign/core/Section'
import {Selector} from '@astryxdesign/core/Selector'
import {StatusDot} from '@astryxdesign/core/StatusDot'
import {Switch} from '@astryxdesign/core/Switch'
import {Text} from '@astryxdesign/core/Text'
import {TextInput} from '@astryxdesign/core/TextInput'
import {VStack} from '@astryxdesign/core/VStack'
import {ArrowUpRight, ClipboardCheck, EyeOff, KeyRound, LockKeyhole, Monitor, Radio, ShieldCheck} from 'lucide-react'
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

function GroupHeading({icon, children, number, description}: {icon: typeof ShieldCheck; children: string; number: string; description?: string}) {
  useLocale()
  return (
    <HStack align="start" className="pd-settings-heading" gap={4}>
      <Text className="pd-settings-number" type="supporting">{number}</Text>
      <VStack gap={2}>
        <HStack align="center" gap={2}>
          <Icon color="secondary" icon={icon} />
          <Heading level={2}>{children}</Heading>
        </HStack>
        {description ? <Text color="secondary">{description}</Text> : null}
      </VStack>
    </HStack>
  )
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

export function ChangeSecurityCode({action}: {action: ActionCallback}) {
  useLocale()
  const [editing, setEditing] = useState(false)
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
  const settings = state.settings
  return (
    <AuthenticatedScreen
      screen="settings"
      title={t("Settings")}
      actions={<Button clickAction={() => action('lock')} icon={<Icon icon={LockKeyhole} />} label={t("Lock Peaks")} />}>
      <HStack className="pd-settings-layout" align="start" gap={10}>
        <VStack as="nav" aria-label={t("Preference sections")} className="pd-settings-index" gap={2}>
          <Text className="peaks-eyebrow" color="secondary" type="supporting">{t("ON THIS PAGE")}</Text>
          {[
            {id: 'privacy', label: 'Privacy & security', icon: ShieldCheck},
            {id: 'appearance', label: 'Appearance', icon: Monitor},
            {id: 'data', label: 'Riot data', icon: Radio},
            {id: 'discord', label: 'Discord', icon: Radio},
          ].map(item => <Button key={item.id} className="pd-settings-index-link" label={t(item.label)} variant="ghost" icon={<Icon icon={item.icon} />} endContent={<Icon icon={ArrowUpRight} size="sm" />} onClick={() => document.getElementById(`pd-settings-${item.id}`)?.scrollIntoView({behavior: settings.reduceMotion || window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth', block: 'start'})} />)}
        </VStack>
      <VStack className="pd-settings-sections" gap={10}>
        <Section id="pd-settings-privacy" className="pd-settings-group" padding={0} variant="transparent">
          <List
            density="spacious"
            hasDividers
            header={<GroupHeading icon={ShieldCheck} number="01">{t("Privacy & security")}</GroupHeading>}>
            <ListItem
              startContent={<Icon icon={LockKeyhole} color="secondary" />}
              description={<Text color="secondary">{settings.autoLockMinutes === 0
                ? t("Stay unlocked until you close Peaks. You can still lock it manually.")
                : t("Lock Peaks after this period without interaction.")}</Text>}
              endContent={
                <Selector
                  isLabelHidden
                  label={t("Automatic lock interval")}
                  onChange={value => { void action('settings', {autoLockMinutes: Number(value)}) }}
                  options={autoLockOptions()}
                  size="sm"
                  value={String(settings.autoLockMinutes)}
                />
              }
              label={t("Automatic lock")}
            />
            <ListItem
              startContent={<Icon icon={EyeOff} color="secondary" />}
              label={t("Streamer Mode")}
              description={<Text color="secondary">{t("Replace everyone’s names with Player 1, Player 2, and so on throughout Peaks.")}</Text>}
              endContent={<Switch label={t("Streamer Mode")} isLabelHidden size="sm"
                value={Boolean(settings.streamerMode)}
                changeAction={value => action('settings', {streamerMode: value}, true)} />}
            />
            <ListItem
              startContent={<Icon icon={ClipboardCheck} color="secondary" />}
              description={<Text color="secondary">{t('Copied authentication codes clear after {{count}} seconds.', {count: settings.clipboardClearSeconds})}</Text>}
              endContent={
                <HStack align="center" gap={2}>
                  <StatusDot label={t("Clipboard safety enabled")} variant="neutral" />
                  <Text type="supporting">{t("Always on")}</Text>
                </HStack>
              }
              label={t("Clipboard safety")}
            />
            <TelemetrySettings />
          </List>
          <VStack className="pd-settings-inset" gap={3}>
            <Text weight="semibold">{t("Security code")}</Text>
            <Text color="secondary">{t("Change the four-digit code that unlocks Peaks.")}</Text>
            <ChangeSecurityCode action={action} />
          </VStack>
        </Section>

        <Section id="pd-settings-appearance" className="pd-settings-group" padding={0} variant="transparent">
          <List
            density="spacious"
            hasDividers
            header={<GroupHeading icon={Monitor} number="02">{t("Appearance")}</GroupHeading>}>
            <ListItem label={t('Language')}
              description={t('Choose the language used in Peaks.')}
              endContent={<LanguageSelector isLabelHidden />} />
            <ListItem
              description={<Text color="secondary">{t("Limit animations and ambient effects.")}</Text>}
              endContent={
                <Switch
                  changeAction={value => action('settings', {reduceMotion: value})}
                  isLabelHidden
                  label={t("Reduce motion")}
                  size="sm"
                  value={settings.reduceMotion}
                />
              }
              label={t("Reduce motion")}
            />
          </List>
        </Section>

        <Section id="pd-settings-data" className="pd-settings-group" padding={0} variant="transparent">
          <List
            density="spacious"
            hasDividers
            header={<GroupHeading icon={Radio} number="03">{t("Riot data")}</GroupHeading>}>
            <ListItem
              description={<Text color="secondary">{t("Use your signed-in Riot client.")}</Text>}
              endContent={
                <HStack align="center" gap={2}>
                  <StatusDot label={t("Keyless player search available")} variant="neutral" />
                  <Text type="supporting">{t("No key required")}</Text>
                </HStack>
              }
              label={t("Player search")}
            />
            <ListItem
              description={
                <Text color="secondary">
                  {settings.riotApiConfigured
                    ? t("An API key is configured for League and TFT statistics.")
                    : t("Add an optional key for more League and TFT statistics.")}
                </Text>
              }
              endContent={
                <HStack align="center" gap={2}>
                  <StatusDot label={settings.riotApiConfigured ? t("Configured") : t("Optional")} variant="neutral" />
                  <Text type="supporting">{settings.riotApiConfigured ? t("Configured") : t("Optional")}</Text>
                </HStack>
              }
              label={t("Developer API key")}
            />
          </List>
          <VStack className="pd-settings-inset" gap={3}>
            <Text weight="semibold">{settings.riotApiConfigured ? t("Replace API key") : t("Add API key")}</Text>
            <ApiKeyControl action={action} />
          </VStack>
        </Section>

        <Section id="pd-settings-discord" className="pd-settings-group" padding={0} variant="transparent">
          <DiscordPresenceSettings header={<GroupHeading icon={Radio} number="04">{t("Discord")}</GroupHeading>} />
        </Section>
        <HStack><Button label={t('What’s new in Peaks')} onClick={() => setNotesOpen(true)} variant="ghost" /></HStack>
        <ReleaseNotesDialog isOpen={notesOpen} onClose={() => setNotesOpen(false)} />

      </VStack>
      </HStack>
    </AuthenticatedScreen>
  )
}
