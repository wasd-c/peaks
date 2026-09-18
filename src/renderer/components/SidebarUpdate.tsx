import {t, useLocale, displayText} from '../i18n'
import {useEffect, useRef, useState} from 'react'
import {Button} from '@astryxdesign/core/Button'
import {Icon} from '@astryxdesign/core/Icon'
import {ProgressBar} from '@astryxdesign/core/ProgressBar'
import {Text} from '@astryxdesign/core/Text'
import {VStack} from '@astryxdesign/core/VStack'
import {Download, RefreshCw, RotateCcw} from 'lucide-react'
import {updateControl, type UpdateState} from '../updateState'

export function UpdateControl({state, onAction}: {state: UpdateState; onAction: () => void}) {
  useLocale()
  const control = updateControl(state)
  if (!control.visible) return null
  const progress = state.phase === 'downloading'
  const restarting = state.phase === 'ready' || state.phase === 'installing'
  return (
    <VStack gap={1} align="center" width="100%" paddingInline={3} aria-label={t("Peaks updates")}>
      <Button
        label={displayText(control.busy ? state.message : control.label)}
        tooltip={displayText(state.message)}
        isIconOnly
        icon={<Icon icon={state.phase === 'error' ? RotateCcw : control.install ? Download : RefreshCw} />}
        variant={control.install ? 'primary' : 'ghost'}
        isLoading={control.busy && !progress}
        isDisabled={control.busy}
        onClick={onAction}
      />
      {progress ? <VStack width="100%"><ProgressBar label={t("Downloading Peaks update")} isLabelHidden value={state.percent ?? 0} variant="neutral" /></VStack> : null}
      {control.caption ? <Text type="supporting" size="2xs" color={control.install ? 'primary' : 'secondary'} hasTabularNumbers role="status" aria-live={progress ? 'off' : 'polite'}>{restarting ? t("Restarting") : displayText(control.caption)}</Text> : null}
    </VStack>
  )
}

export function SidebarUpdate() {
  useLocale()
  const [preview] = useState<'available' | 'downloading' | 'error' | null>(() => {
    if (!import.meta.env.DEV || typeof window === 'undefined' || window.peaks) return null
    const phase = new URLSearchParams(window.location.search).get('updatePreview')
    return phase === 'available' || phase === 'downloading' || phase === 'error' ? phase : null
  })
  const [state, setState] = useState<UpdateState | null>(() => preview ? {
    phase: preview, currentVersion: '0.3.0', version: '0.4.0', percent: preview === 'downloading' ? 37 : undefined,
    retry: preview === 'error' ? 'install' : undefined,
    message: 'Preview · Peaks 0.4.0 is available. Update and restart.',
  } : null)
  const requestVersion = useRef(0)
  const active = useRef(false)
  const actionPending = useRef(false)
  const rapid = state?.phase === 'downloading' || state?.phase === 'ready' || state?.phase === 'installing' || state?.phase === 'checking'

  useEffect(() => {
    if (preview) {
      if (state?.phase !== 'downloading') return
      const timer = setInterval(() => setState(previous => {
        if (!previous) return previous
        const percent = Math.min(100, (previous.percent ?? 0) + 1)
        return {...previous, percent, phase: percent === 100 ? 'ready' : 'downloading', message: 'Preview · Downloading update. No update will be installed.'}
      }), 500)
      return () => clearInterval(timer)
    }
    if (!window.peaks) return
    active.current = true
    let disposed = false
    let timer: ReturnType<typeof setTimeout> | undefined
    const refresh = async () => {
      const version = requestVersion.current
      try {
        const next = await window.peaks!.invoke<UpdateState>('update_status')
        if (!disposed && version === requestVersion.current && !actionPending.current) setState(next)
      } catch { /* The next poll recovers if the native process is briefly busy. */ }
      finally { if (!disposed) timer = setTimeout(() => { void refresh() }, rapid ? 750 : 10_000) }
    }
    void refresh()
    return () => {
      disposed = true
      active.current = false
      clearTimeout(timer)
    }
  }, [rapid, preview, state?.phase])

  const act = async () => {
    if (preview) {
      if (state && !updateControl(state).busy) setState({...state, phase: 'downloading', percent: 0})
      return
    }
    if (!state || !window.peaks || actionPending.current || updateControl(state).busy) return
    actionPending.current = true
    ++requestVersion.current
    const {command, install} = updateControl(state)
    setState({...state, phase: install ? 'downloading' : 'checking', percent: install ? 0 : undefined, message: install ? 'Downloading update. Peaks will restart when it is ready.' : 'Checking for updates…'})
    try {
      const next = await window.peaks.invoke<UpdateState>(command)
      if (active.current) setState(next)
    } catch {
      if (active.current) setState({...state, phase: 'error', retry: install ? 'install' : 'check', message: 'Peaks could not start the update. Try again.'})
    } finally { actionPending.current = false }
  }

  return state ? <UpdateControl state={state} onAction={() => { void act() }} /> : null
}
