import type {AccountConnection} from './accountConnection'

export interface AccountConnectionCallbacks {
  approve: (accountId: string) => Promise<void>
  cancel?: () => Promise<void>
  onError: (error: unknown) => void
  onChange: (connection: AccountConnection | null) => void
}

/** One identity-bound approval, including its completion animation, at a time. */
export function createAccountConnectionController({approve, cancel: cancelApproval, onError, onChange}: AccountConnectionCallbacks) {
  let disposed = false
  let active = false
  let attempt = 0
  let timer: ReturnType<typeof setTimeout> | undefined

  const connect = async (accountId: string): Promise<void> => {
    if (disposed || active) return
    active = true
    const currentAttempt = ++attempt
    onChange({accountId, phase: 'pending'})
    try {
      await approve(accountId)
    } catch (error) {
      if (disposed || currentAttempt !== attempt) return
      active = false
      onChange(null)
      onError(error)
      return
    }
    if (disposed || currentAttempt !== attempt) return
    onChange({accountId, phase: 'approved'})
    timer = setTimeout(() => {
      if (disposed || currentAttempt !== attempt) return
      onChange({accountId, phase: 'leaving'})
      timer = setTimeout(() => {
        if (disposed || currentAttempt !== attempt) return
        timer = undefined
        active = false
        onChange(null)
      }, 650)
    }, 800)
  }

  const cancel = async () => {
    if (!active || disposed) return
    attempt += 1
    active = false
    if (timer !== undefined) clearTimeout(timer)
    timer = undefined
    onChange(null)
    await cancelApproval?.()
  }

  const dispose = () => {
    disposed = true
    active = false
    if (timer !== undefined) clearTimeout(timer)
    timer = undefined
  }

  return {connect, cancel, dispose}
}
