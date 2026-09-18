import type {AccountConnection} from './accountConnection'

export interface AccountConnectionCallbacks {
  approve: (accountId: string) => Promise<void>
  onError: (error: unknown) => void
  onChange: (connection: AccountConnection | null) => void
}

/** One identity-bound approval, including its completion animation, at a time. */
export function createAccountConnectionController({approve, onError, onChange}: AccountConnectionCallbacks) {
  let disposed = false
  let active = false
  let timer: ReturnType<typeof setTimeout> | undefined

  const connect = async (accountId: string): Promise<void> => {
    if (disposed || active) return
    active = true
    onChange({accountId, phase: 'pending'})
    try {
      await approve(accountId)
    } catch (error) {
      if (disposed) return
      active = false
      onChange(null)
      onError(error)
      return
    }
    if (disposed) return
    onChange({accountId, phase: 'approved'})
    timer = setTimeout(() => {
      if (disposed) return
      onChange({accountId, phase: 'leaving'})
      timer = setTimeout(() => {
        if (disposed) return
        timer = undefined
        active = false
        onChange(null)
      }, 650)
    }, 800)
  }

  const dispose = () => {
    disposed = true
    active = false
    if (timer !== undefined) clearTimeout(timer)
    timer = undefined
  }

  return {connect, dispose}
}
