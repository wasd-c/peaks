import {useCallback, useEffect, useRef, useState} from 'react'
import type {AccountConnection} from './accountConnection'
import {createAccountConnectionController} from './accountConnectionController'

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
  return {connection, connect}
}
