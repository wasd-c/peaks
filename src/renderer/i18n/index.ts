import i18next, {type TOptions} from 'i18next'
import {initReactI18next, useTranslation} from 'react-i18next'
import en from './locales/en.json'
import fr from './locales/fr.json'
import ko from './locales/ko.json'

export const LANGUAGES = [
  {value: 'en', label: 'English'},
  {value: 'fr', label: 'Français'},
  {value: 'ko', label: '한국어'},
] as const
export type Language = typeof LANGUAGES[number]['value']
export const LANGUAGE_STORAGE_KEY = 'peaks.language.v1'
export const localeTags: Record<Language, string> = {en: 'en-US', fr: 'fr-FR', ko: 'ko-KR'}
const displayKeys = new Map(Object.keys(en).map(key => [key.toLowerCase(), key]))

export function supportedLanguage(value?: string | null): Language | undefined {
  const base = value?.toLowerCase().split(/[-_]/)[0]
  return base === 'en' || base === 'fr' || base === 'ko' ? base : undefined
}

export function detectLanguage(saved?: string | null, preferred: readonly string[] = []): Language {
  return supportedLanguage(saved) ?? preferred.map(supportedLanguage).find(Boolean) ?? 'en'
}

// Bundled catalogs make both startup and language changes synchronous and offline.
export const i18n = i18next.createInstance()
void i18n.use(initReactI18next).init({
  lng: 'en', fallbackLng: 'en', supportedLngs: ['en', 'fr', 'ko'],
  resources: {en: {translation: en}, fr: {translation: fr}, ko: {translation: ko}},
  initAsync: false, keySeparator: false, nsSeparator: false,
  interpolation: {escapeValue: false}, returnNull: false,
})

export function getLanguage(): Language { return supportedLanguage(i18n.resolvedLanguage) ?? 'en' }

export function t(key: string, options?: TOptions): string {
  return i18n.t(key, {...options, defaultValue: key}) as string
}

/** Subscribe wherever translated copy is rendered, including stand-alone dialogs. */
export function useLocale(): Language {
  useTranslation(undefined, {i18n})
  return getLanguage()
}

function applyLanguage(language: Language) {
  if (!supportedLanguage(language)) return
  void i18n.changeLanguage(language)
  if (typeof document !== 'undefined') {
    document.documentElement.lang = language
    document.documentElement.dir = 'ltr'
  }
}

export function setLanguage(language: Language) {
  if (!supportedLanguage(language)) return
  try { window.localStorage.setItem(LANGUAGE_STORAGE_KEY, language) } catch { /* Session-only when storage is unavailable. */ }
  applyLanguage(language)
}

export function initializeLanguage() {
  let saved: string | null = null
  try { saved = window.localStorage.getItem(LANGUAGE_STORAGE_KEY) } catch { /* Use the system language. */ }
  applyLanguage(detectLanguage(saved, navigator.languages?.length ? navigator.languages : [navigator.language]))
}

export function formatNumber(value: number, options?: Intl.NumberFormatOptions): string {
  return new Intl.NumberFormat(localeTags[getLanguage()], options).format(value)
}

/** Localize known display values without changing game IDs, identities or asset lookups. */
export function displayText(value?: string | null): string {
  if (!value) return value ?? ''
  if (i18n.exists(value)) return t(value)
  const canonical = displayKeys.get(value.toLowerCase())
  if (canonical) return t(canonical)
  const rank = /^(Iron|Bronze|Silver|Gold|Platinum|Emerald|Diamond|Master|Grandmaster|Challenger|Ascendant|Immortal|Radiant)(\s+[\dIVX]+)?$/i.exec(value)
  if (rank) return `${t(rank[1][0].toUpperCase() + rank[1].slice(1).toLowerCase())}${rank[2] ?? ''}`
  const relative = /^(\d+)\s*(seconds?|secs?|s|minutes?|mins?|m|hours?|hrs?|h|days?|d|weeks?|w|months?|years?|y) ago$/i.exec(value)
  if (relative && getLanguage() !== 'en') {
    const units: Record<string, Intl.RelativeTimeFormatUnit> = {s: 'second', m: 'minute', h: 'hour', d: 'day', w: 'week', y: 'year'}
    const unit = relative[2].toLowerCase().startsWith('month') ? 'month' : units[relative[2][0].toLowerCase()]
    return new Intl.RelativeTimeFormat(localeTags[getLanguage()], {numeric: 'auto'}).format(-Number(relative[1]), unit)
  }
  const team = /^(Team|Duo|Player|Party)\s+(\d+)$/i.exec(value)
  if (team) return t(`${team[1][0].toUpperCase() + team[1].slice(1).toLowerCase()} {{number}}`, {number: team[2]})
  const update = /^Peaks (\d+\.\d+\.\d+) is available\. Update and restart\.$/.exec(value)
  if (update) return t('Peaks {{version}} is available. Update and restart.', {version: update[1]})
  const control = /^Update to Peaks (\d+\.\d+\.\d+) and restart$/.exec(value)
  if (control) return t('Update to Peaks {{version}} and restart', {version: control[1]})
  if (value.includes(' · ')) return value.split(' · ').map(displayText).join(' · ')
  return value
}
