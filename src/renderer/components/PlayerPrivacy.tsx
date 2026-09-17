import {createContext, useContext, useMemo, useState, type ReactNode} from 'react'
import {PlayerAliases} from '../privacy'
import type {AppState} from '../types'

const PlayerPrivacyContext = createContext({
  enabled: false,
  displayName: (identity: string) => identity,
  redact: (text: string) => text,
})

export function PlayerPrivacyProvider({state, children}: {state: AppState; children: ReactNode}) {
  const [aliases] = useState(() => {
    const initial = new PlayerAliases()
    initial.seed(state)
    return initial
  })
  const enabled = Boolean(state.settings.streamerMode)
  const privacy = useMemo(() => ({
    enabled,
    displayName: (identity: string) => enabled ? aliases.name(identity) : identity,
    redact: (text: string) => enabled ? aliases.redact(text) : text,
  }), [aliases, enabled])
  return <PlayerPrivacyContext.Provider value={privacy}>{children}</PlayerPrivacyContext.Provider>
}

export const usePlayerPrivacy = () => useContext(PlayerPrivacyContext)
