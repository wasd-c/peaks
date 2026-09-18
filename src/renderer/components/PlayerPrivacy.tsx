import {createContext, useContext, useMemo, useState, type ReactNode} from 'react'
import {PlayerAliases} from '../privacy'
import {t, useLocale} from '../i18n'
import type {AppState} from '../types'

const PlayerPrivacyContext = createContext({
  enabled: false,
  displayName: (identity: string) => identity,
  redact: (text: string) => text,
})

export function PlayerPrivacyProvider({state, children}: {state: AppState; children: ReactNode}) {
  const language = useLocale()
  const [aliases] = useState(() => {
    const initial = new PlayerAliases()
    initial.seed(state)
    return initial
  })
  const enabled = Boolean(state.settings.streamerMode)
  const privacy = useMemo(() => ({
    enabled,
    displayName: (identity: string) => enabled ? t('Player {{number}}', {number: aliases.name(identity).slice(7), lng: language}) : identity,
    redact: (text: string) => enabled ? aliases.redact(text).replace(/\bPlayer (\d+)\b/g, (_match, number: string) => t('Player {{number}}', {number, lng: language})) : text,
  }), [aliases, enabled, language])
  return <PlayerPrivacyContext.Provider value={privacy}>{children}</PlayerPrivacyContext.Provider>
}

export const usePlayerPrivacy = () => useContext(PlayerPrivacyContext)
