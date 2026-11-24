import {useLayoutEffect, useRef, useState, type ReactNode} from 'react'
import {VStack} from '../ui'

/** Keep the previous workspace visible beneath an arriving account page. */
export function AccountArrival({arrival, children, fitContent = false}: {arrival: number; children: ReactNode; fitContent?: boolean}) {
  const previous = useRef<ReactNode>(null)
  const lastArrival = useRef(arrival)
  const [backdrop, setBackdrop] = useState<ReactNode>(null)
  useLayoutEffect(() => {
    if (arrival === lastArrival.current) return
    lastArrival.current = arrival
    setBackdrop(previous.current)
    // Reduced motion may disable animation events entirely.
    const timeout = window.setTimeout(() => setBackdrop(null), 1_000)
    return () => window.clearTimeout(timeout)
  }, [arrival])
  useLayoutEffect(() => { previous.current = children }, [children])
  return <VStack className="pd-account-arrival" height={fitContent ? undefined : '100%'}>
    {backdrop ? <VStack className="pd-account-arrival__backdrop" aria-hidden inert>{backdrop}</VStack> : null}
    <VStack className={backdrop ? 'pd-account-arrival__front pd-account-arrival__front--enter' : 'pd-account-arrival__front'}
      key={arrival} height={fitContent ? undefined : '100%'} onAnimationEnd={event => {
        if (event.target === event.currentTarget) setBackdrop(null)
      }}>{children}</VStack>
  </VStack>
}
