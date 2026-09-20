import {useCallback, useEffect, useMemo, useRef, useState} from 'react'
import {createProfileRefreshController, type ProfileRefreshPhase} from './profileRefreshController'

/** A new identity gets a new controller even when an earlier request is pending. */
export function useProfileRefresh(accountId: string | undefined, onRefresh: (() => Promise<void>) | undefined) {
  const enabled = Boolean(onRefresh)
  const identity = useMemo(() => ({accountId, enabled}), [accountId, enabled])
  const [revision, setRevision] = useState(0)
  const [status, setStatus] = useState<{identity: typeof identity; phase: ProfileRefreshPhase} | null>(null)
  const callbacks = useRef({onRefresh})
  const controller = useRef<ReturnType<typeof createProfileRefreshController> | null>(null)
  useEffect(() => { callbacks.current = {onRefresh} }, [onRefresh])
  useEffect(() => {
    if (!identity.accountId || !identity.enabled) return
    const current = createProfileRefreshController({
      request: async () => { await callbacks.current.onRefresh?.() },
      onPhase: phase => setStatus({identity, phase}),
      onSuccess: () => setRevision(value => value + 1),
    })
    controller.current = current
    return () => { current.dispose(); controller.current = null }
  }, [identity])
  const refresh = useCallback(() => controller.current?.refresh() ?? Promise.resolve(), [])
  return {refresh, revision, failed: status?.identity === identity && status.phase === 'failed'}
}
