import {t, useLocale, displayText} from '../i18n'
import {useEffect, useRef, useState} from 'react'
import {HStack} from '@astryxdesign/core/HStack'
import {ListItem} from '@astryxdesign/core/List'
import {Switch} from '@astryxdesign/core/Switch'
import {Text} from '@astryxdesign/core/Text'
import {invoke} from '../bridge'

interface TelemetryStatus {enabled: boolean; available: boolean}

export function TelemetrySettings() {
  useLocale()
  const [status, setStatus] = useState<TelemetryStatus | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const active = useRef(false)
  const saving = useRef(false)
  useEffect(() => {
    active.current = true
    let cancelled = false
    const load = async () => {
      try {
        const value = await invoke<TelemetryStatus>('telemetry_settings')
        if (!cancelled) setStatus(value)
      } catch {
        if (!cancelled) setError('Could not load this preference. Reopen Settings to retry.')
      }
    }
    void load()
    return () => {cancelled = true; active.current = false}
  }, [])
  const update = async (enabled: boolean) => {
    if (saving.current) return
    saving.current = true
    setBusy(true)
    setError('')
    try {
      const value = await invoke<TelemetryStatus>('telemetry_settings', {enabled})
      if (active.current) setStatus(value)
    } catch {
      if (active.current) setError('Could not save this preference. Please try again.')
    } finally {
      saving.current = false
      if (active.current) setBusy(false)
    }
  }
  return <ListItem
    label={t("Share app diagnostics")}
    description={<Text color="secondary">{displayText(error) || t("Help improve Peaks with performance and error counts. No account or match data is sent.")}</Text>}
    endContent={<HStack gap={3} align="center">
      <Text type="supporting">{status ? status.enabled ? t("On") : t("Off") : '…'}</Text>
      <Switch label={t("Share app diagnostics")} isLabelHidden size="sm" value={status?.enabled ?? false}
        isDisabled={!status || busy || !status.available} isLoading={busy || (!status && !error)} changeAction={update} />
    </HStack>}
  />
}
