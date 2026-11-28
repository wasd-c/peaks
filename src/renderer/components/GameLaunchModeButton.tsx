import {useRef, useState} from 'react'
import {Check, Gamepad2, HelpCircle, X, type LucideIcon} from 'lucide-react'
import {Button, Icon, useToast} from '../ui'
import {invoke} from '../bridge'
import {displayText, t, useLocale} from '../i18n'
import type {AppState, GameLaunchMode} from '../types'

const NEXT: Record<GameLaunchMode, GameLaunchMode> = {favorite: 'ask', ask: 'off', off: 'favorite'}
const BADGE: Record<GameLaunchMode, LucideIcon> = {favorite: Check, ask: HelpCircle, off: X}
const DESCRIPTION: Record<GameLaunchMode, string> = {
  favorite: 'Launch your favorite game when you use an account',
  ask: 'Choose a game each time you use an account',
  off: 'Do not launch a game when you use an account',
}

export const gameLaunchMode = (state: AppState): GameLaunchMode =>
  state.settings.gameLaunchMode ?? (state.settings.autoLaunchFavoriteGame ? 'favorite' : 'off')

/** Cycles what "Use" does with games: launch the favorite, ask which one, or none. */
export function GameLaunchModeButton({state, onStateChange}: {
  state: AppState
  onStateChange: (state: AppState) => void
}) {
  useLocale()
  const showToast = useToast()
  const [pending, setPending] = useState(false)
  const inFlight = useRef(false)
  const mode = gameLaunchMode(state)

  const cycle = async () => {
    if (inFlight.current) return
    inFlight.current = true
    setPending(true)
    try {
      onStateChange(await invoke<AppState>('settings', {gameLaunchMode: NEXT[mode]}))
    } catch (error) {
      showToast({body: displayText(error instanceof Error ? error.message : 'That action could not be completed'),
        type: 'error', uniqueID: 'game-launch-mode', isAutoHide: true})
    } finally {
      inFlight.current = false
      setPending(false)
    }
  }

  const description = t(DESCRIPTION[mode])
  return <Button className="pd-launch-mode" data-mode={mode} label={description} tooltip={description}
    variant="ghost" isIconOnly isDisabled={pending} clickAction={cycle}
    icon={<span className="pd-launch-mode__glyph" aria-hidden="true">
      <Icon icon={Gamepad2} />
      <span className="pd-launch-mode__badge"><Icon icon={BADGE[mode]} size="sm" /></span>
    </span>} />
}
