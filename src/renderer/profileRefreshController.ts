export type ProfileRefreshPhase = 'pending' | 'failed' | 'idle'

/** A failed request stays local; React transition actions must always settle. */
export function createProfileRefreshController({request, onPhase, onSuccess}: {
  request: () => Promise<void>
  onPhase: (phase: ProfileRefreshPhase) => void
  onSuccess: () => void
}) {
  let disposed = false
  let pending: Promise<void> | undefined

  const refresh = (): Promise<void> => {
    if (disposed) return Promise.resolve()
    if (pending) return pending
    onPhase('pending')
    pending = (async () => {
      try {
        await request()
      } catch {
        if (!disposed) onPhase('failed')
        return
      }
      if (!disposed) { onSuccess(); onPhase('idle') }
    })().finally(() => { pending = undefined })
    return pending
  }

  return {refresh, dispose: () => { disposed = true }}
}
