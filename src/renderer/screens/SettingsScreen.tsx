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
import {passcodeErrorMessage} from '../passcodeMessages'
import {AuthenticatedScreen, type ActionCallback} from './shared'

const AUTO_LOCK_OPTIONS = [{label: 'Only when Peaks closes', value: '0'}, ...[1, 5, 15, 30, 60].map(minutes => ({
  label: `${minutes} minute${minutes === 1 ? '' : 's'}`,
  value: String(minutes),
}))]

export interface SettingsScreenProps {
  state: AppState
  action: ActionCallback
}

function GroupHeading({icon, children, number, description}: {icon: typeof ShieldCheck; children: string; number: string; description?: string}) {
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
  const [key, setKey] = useState('')
  return (
    <HStack align="end" className="pd-settings-api-control" gap={2}>
      <TextInput
        isLabelHidden
        label="Riot developer API key"
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
        label="Save key"
      />
    </HStack>
  )
}

export function ChangeSecurityCode({action}: {action: ActionCallback}) {
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
      setError(passcodeErrorMessage(failure, 'Impossible de modifier le mot de passe. Réessaie.'))
    } finally {
      setBusy(false)
    }
  }
  if (!editing) return (
    <Button icon={<Icon icon={KeyRound} />} label="Change security code" clickAction={() => setEditing(true)} />
  )
  return (
    <VStack gap={4}>
      <FormLayout>
        <TextInput label="Current security code" type="password"
          isDisabled={busy} value={oldPin} onChange={value => { if (/^[0-9]{0,4}$/.test(value)) setOldPin(value) }} />
        <TextInput label="New security code" type="password"
          description="Choose four digits." isDisabled={busy} value={newPin} onChange={value => { if (/^[0-9]{0,4}$/.test(value)) setNewPin(value) }} />
        <TextInput label="Confirm new security code" type="password"
          isDisabled={busy} value={confirmPin} onChange={value => { if (/^[0-9]{0,4}$/.test(value)) setConfirmPin(value) }} onEnter={() => { void save() }} />
      </FormLayout>
      {error ? <Text role="alert">{error}</Text> : null}
      <HStack gap={2}>
        <Button label="Save new code" variant="primary" isDisabled={!valid} isLoading={busy} clickAction={save} />
        <Button label="Cancel" variant="ghost" isDisabled={busy} clickAction={() => { clear(); setEditing(false) }} />
      </HStack>
    </VStack>
  )
}

export function SettingsScreen({state, action}: SettingsScreenProps) {
  const settings = state.settings
  return (
    <AuthenticatedScreen
      screen="settings"
      title="Settings"
      actions={<Button clickAction={() => action('lock')} icon={<Icon icon={LockKeyhole} />} label="Lock Peaks" />}>
      <HStack className="pd-settings-layout" align="start" gap={10}>
        <VStack as="nav" aria-label="Preference sections" className="pd-settings-index" gap={2}>
          <Text className="peaks-eyebrow" color="secondary" type="supporting">ON THIS PAGE</Text>
          {[
            {id: 'privacy', label: 'Privacy & security', icon: ShieldCheck},
            {id: 'appearance', label: 'Appearance', icon: Monitor},
            {id: 'data', label: 'Riot data', icon: Radio},
            {id: 'discord', label: 'Discord', icon: Radio},
          ].map(item => <Button key={item.id} className="pd-settings-index-link" label={item.label} variant="ghost" icon={<Icon icon={item.icon} />} endContent={<Icon icon={ArrowUpRight} size="sm" />} onClick={() => document.getElementById(`pd-settings-${item.id}`)?.scrollIntoView({behavior: settings.reduceMotion || window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth', block: 'start'})} />)}
        </VStack>
      <VStack className="pd-settings-sections" gap={10}>
        <Section id="pd-settings-privacy" className="pd-settings-group" padding={0} variant="transparent">
          <List
            density="spacious"
            hasDividers
            header={<GroupHeading icon={ShieldCheck} number="01">Privacy & security</GroupHeading>}>
            <ListItem
              startContent={<Icon icon={LockKeyhole} color="secondary" />}
              description={<Text color="secondary">{settings.autoLockMinutes === 0
                ? 'Stay unlocked until you close Peaks. You can still lock it manually.'
                : 'Lock Peaks after this period without interaction.'}</Text>}
              endContent={
                <Selector
                  isLabelHidden
                  label="Automatic lock interval"
                  onChange={value => { void action('settings', {autoLockMinutes: Number(value)}) }}
                  options={AUTO_LOCK_OPTIONS}
                  size="sm"
                  value={String(settings.autoLockMinutes)}
                />
              }
              label="Automatic lock"
            />
            <ListItem
              startContent={<Icon icon={EyeOff} color="secondary" />}
              label="Streamer Mode"
              description={<Text color="secondary">Replace everyone’s names with Player 1, Player 2, and so on throughout Peaks.</Text>}
              endContent={<Switch label="Streamer Mode" isLabelHidden size="sm"
                value={Boolean(settings.streamerMode)}
                changeAction={value => action('settings', {streamerMode: value}, true)} />}
            />
            <ListItem
              startContent={<Icon icon={ClipboardCheck} color="secondary" />}
              description={<Text color="secondary">Copied authentication codes clear after {settings.clipboardClearSeconds} seconds.</Text>}
              endContent={
                <HStack align="center" gap={2}>
                  <StatusDot label="Clipboard safety enabled" variant="neutral" />
                  <Text type="supporting">Always on</Text>
                </HStack>
              }
              label="Clipboard safety"
            />
            <TelemetrySettings />
          </List>
          <VStack className="pd-settings-inset" gap={3}>
            <Text weight="semibold">Security code</Text>
            <Text color="secondary">Change the four-digit code that unlocks Peaks.</Text>
            <ChangeSecurityCode action={action} />
          </VStack>
        </Section>

        <Section id="pd-settings-appearance" className="pd-settings-group" padding={0} variant="transparent">
          <List
            density="spacious"
            hasDividers
            header={<GroupHeading icon={Monitor} number="02">Appearance</GroupHeading>}>
            <ListItem
              description={<Text color="secondary">Limit animations and ambient effects.</Text>}
              endContent={
                <Switch
                  changeAction={value => action('settings', {reduceMotion: value})}
                  isLabelHidden
                  label="Reduce motion"
                  size="sm"
                  value={settings.reduceMotion}
                />
              }
              label="Reduce motion"
            />
          </List>
        </Section>

        <Section id="pd-settings-data" className="pd-settings-group" padding={0} variant="transparent">
          <List
            density="spacious"
            hasDividers
            header={<GroupHeading icon={Radio} number="03">Riot data</GroupHeading>}>
            <ListItem
              description={<Text color="secondary">Use your signed-in Riot client.</Text>}
              endContent={
                <HStack align="center" gap={2}>
                  <StatusDot label="Keyless player search available" variant="neutral" />
                  <Text type="supporting">No key required</Text>
                </HStack>
              }
              label="Player search"
            />
            <ListItem
              description={
                <Text color="secondary">
                  {settings.riotApiConfigured
                    ? 'An API key is configured for League and TFT statistics.'
                    : 'Add an optional key for more League and TFT statistics.'}
                </Text>
              }
              endContent={
                <HStack align="center" gap={2}>
                  <StatusDot label={settings.riotApiConfigured ? 'Configured' : 'Optional'} variant="neutral" />
                  <Text type="supporting">{settings.riotApiConfigured ? 'Configured' : 'Optional'}</Text>
                </HStack>
              }
              label="Developer API key"
            />
          </List>
          <VStack className="pd-settings-inset" gap={3}>
            <Text weight="semibold">{settings.riotApiConfigured ? 'Replace API key' : 'Add API key'}</Text>
            <ApiKeyControl action={action} />
          </VStack>
        </Section>

        <Section id="pd-settings-discord" className="pd-settings-group" padding={0} variant="transparent">
          <DiscordPresenceSettings header={<GroupHeading icon={Radio} number="04">Discord</GroupHeading>} />
        </Section>

      </VStack>
      </HStack>
    </AuthenticatedScreen>
  )
}
