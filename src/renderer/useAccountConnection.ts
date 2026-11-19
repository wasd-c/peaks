import {useCallback, useEffect, useRef, useState} from 'react'
import type {AccountConnection} from './accountConnection'
import {createAccountConnectionController} from './accountConnectionController'
import {invoke} from './bridge'

/** Keep approval alive across overview navigation; serialize identity-bound QR requests. */
export function useAccountConnection({approve, onError}: {
  approve: (accountId: string) => Promise<void>
  onError: (error: unknown) => void
}) {
  const [connection, setConnection] = useState<AccountConnection | null>(null)
  const callbacks = useRef({approve, onError})
  const controller = useRef<ReturnType<typeof createAccountConnectionController> | null>(null)
  useEffect(() => {
    callbacks.current = {approve, onError}
  }, [approve, onError])
  useEffect(() => {
    const current = createAccountConnectionController({
      approve: accountId => callbacks.current.approve(accountId),
      cancel: async () => { await invoke('cancel_connection') },
      onError: error => callbacks.current.onError(error),
      onChange: setConnection,
    })
    controller.current = current
    return () => {
      current.dispose()
      controller.current = null
    }
  }, [])

  const connect = useCallback((accountId: string): Promise<void> => (
    controller.current?.connect(accountId) ?? Promise.resolve()
  ), [])
  const cancel = useCallback((): Promise<void> => (
    controller.current?.cancel() ?? Promise.resolve()
  ), [])
  return {connection, connect, cancel}
}
