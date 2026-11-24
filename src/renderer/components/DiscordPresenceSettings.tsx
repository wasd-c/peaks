import {Card} from 'antd'
import {MessageCircle} from 'lucide-react'
import {t, useLocale, displayText} from '../i18n'
import {useEffect, useRef, useState, type ReactNode} from 'react'
import {HStack, List, ListItem, Switch, Text} from '../ui'
import {invoke} from '../bridge'

interface DiscordPresenceState {
  enabled: boolean
}

export function DiscordPresenceSettings({header}: {header?: ReactNode}) {
  useLocale()
  const [connection, setConnection] = useState<DiscordPresenceState | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [pollError, setPollError] = useState('')
  const active = useRef(false)
  const saving = useRef(false)
  const requestVersion = useRef(0)

  useEffect(() => {
    active.current = true
    let disposed = false
    let timer: ReturnType<typeof setTimeout> | undefined
    const refresh = async () => {
      if (!saving.current) {
        const version = ++requestVersion.current
        try {
          const result = await invoke<DiscordPresenceState>('discord_presence')
          if (disposed || version !== requestVersion.current) return
          setConnection(result)
          setPollError('')
        } catch {
          if (!disposed && version === requestVersion.current) {
            setPollError('Could not load this preference. Retrying.')
          }
        } finally {
          if (!disposed) timer = setTimeout(() => { void refresh() }, 5000)
        }
      } else if (!disposed) {
        timer = setTimeout(() => { void refresh() }, 5000)
      }
    }
    void refresh()
    return () => {
      active.current = false
      disposed = true
      clearTimeout(timer)
    }
  }, [])

  const update = async (enabled: boolean) => {
    if (saving.current) return
    saving.current = true
    ++requestVersion.current
    setBusy(true)
    setError('')
    try {
      const result = await invoke<DiscordPresenceState>('discord_presence', {enabled})
      if (!active.current) return
      setConnection(result)
      setPollError('')
    } catch {
      if (active.current) setError('Could not save this preference. Please try again.')
    } finally {
      saving.current = false
      if (active.current) setBusy(false)
    }
  }

  return (
    <>
      <Card size="small" title={header} styles={{body: {padding: 4}}}><List density="spacious" hasDividers>
        <ListItem
          startContent={<MessageCircle size={16} aria-hidden color="var(--color-text-secondary)" />}
          label={t('Share Discord activity')}
          endContent={<HStack gap={3} align="center">
            <Switch
              label={t('Share Discord activity')}
              isLabelHidden
              size="sm"
              value={connection?.enabled ?? false}
              isLoading={!connection || busy}
              isDisabled={!connection || busy}
              changeAction={update}
            />
          </HStack>}
        />
      </List></Card>
      {error || pollError ? <Text role="alert">{displayText(error || pollError)}</Text> : null}
    </>
  )
}
