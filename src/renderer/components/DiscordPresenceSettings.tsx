import {useEffect, useRef, useState, type ReactNode} from 'react'
import {HStack} from '@astryxdesign/core/HStack'
import {List, ListItem} from '@astryxdesign/core/List'
import {Switch} from '@astryxdesign/core/Switch'
import {Text} from '@astryxdesign/core/Text'
import {invoke} from '../bridge'

interface DiscordPresenceState {
  enabled: boolean
}

export function DiscordPresenceSettings({header}: {header: ReactNode}) {
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
            setPollError('Impossible de charger ce réglage. Nouvelle tentative en cours.')
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
      if (active.current) setError('Impossible d’enregistrer ce réglage. Réessayez.')
    } finally {
      saving.current = false
      if (active.current) setBusy(false)
    }
  }

  return (
    <>
      <List density="spacious" hasDividers header={header}>
        <ListItem
          label="Partage de l’activité Discord"
          endContent={<HStack gap={3} align="center">
            <Text type="supporting">{connection ? connection.enabled ? 'Oui' : 'Non' : '…'}</Text>
            <Switch
              label="Partage de l’activité Discord"
              isLabelHidden
              size="sm"
              value={connection?.enabled ?? false}
              isLoading={!connection || busy}
              isDisabled={!connection || busy}
              changeAction={update}
            />
          </HStack>}
        />
      </List>
      {error || pollError ? <Text role="alert">{error || pollError}</Text> : null}
    </>
  )
}
