import {useLayoutEffect, useRef, useState, type ReactNode} from 'react'
import {VStack} from '../ui'

function RetainedScreen({active, children, viewKey}: {active: boolean; children: ReactNode; viewKey: string}) {
  const root = useRef<HTMLDivElement>(null)
  const positions = useRef(new Map<HTMLElement, {left: number; top: number}>())
  const focused = useRef<HTMLElement | null>(null)
  useLayoutEffect(() => {
    if (!active) return
    const snapshot = [...positions.current]
    const restore = () => {
      for (const [element, position] of snapshot) {
        if (root.current?.contains(element)) element.scrollTo({...position, behavior: 'instant'})
        else positions.current.delete(element)
      }
    }
    restore()
    if (focused.current && root.current?.contains(focused.current)) focused.current.focus({preventScroll: true})
    // A newly visible layout may apply scroll anchoring during this frame.
    const frame = window.requestAnimationFrame(restore)
    return () => window.cancelAnimationFrame(frame)
  }, [active])
  return <VStack ref={root} className="screen-transition" height="100%" data-workspace-view={viewKey}
    hidden={!active} inert={!active} aria-hidden={!active || undefined} style={active ? undefined : {display: 'none'}}
    onScrollCapture={event => {
      if (active && event.target instanceof HTMLElement) positions.current.set(event.target, {left: event.target.scrollLeft, top: event.target.scrollTop})
    }}
    onFocusCapture={event => { if (active && event.target instanceof HTMLElement) focused.current = event.target }}>
    {children}
  </VStack>
}

/** Retain only the active return path, releasing screens when popped or replaced. */
export function WorkspaceHistory({path, children}: {path: string[]; children: ReactNode}) {
  const key = path.at(-1)!
  const pathKey = JSON.stringify(path)
  const [saved, setSaved] = useState(() => ({pathKey, children, views: new Map([[key, children]])}))
  let current = saved
  if (saved.pathKey !== pathKey || saved.children !== children) {
    const views = new Map(path.map(route => [route, route === key ? children : saved.views.get(route)]))
    current = {pathKey, children, views}
    setSaved(current)
  }
  return path.map(route => <RetainedScreen key={route} viewKey={route} active={route === key}>{current.views.get(route)}</RetainedScreen>)
}
