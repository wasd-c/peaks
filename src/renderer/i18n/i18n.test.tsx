import {renderToStaticMarkup} from 'react-dom/server'
import {LayerProvider} from '@astryxdesign/core/Layer'
import {afterEach, describe, expect, it, vi} from 'vitest'
import {detectLanguage, displayText, formatNumber, getLanguage, i18n, initializeLanguage, LANGUAGE_STORAGE_KEY, setLanguage, t} from './index'
import {LocaleProvider} from './LocaleProvider'
import en from './locales/en.json'
import fr from './locales/fr.json'
import ko from './locales/ko.json'
import {LockScreen, RESET_PROMPTS} from '../components/LockScreen'
import {OnboardingScreen, ONBOARDING_ACTION, ONBOARDING_BODY, ONBOARDING_HEADING} from '../components/OnboardingScreen'
import {SettingsScreen} from '../screens/SettingsScreen'
import {PlayerPrivacyProvider, usePlayerPrivacy} from '../components/PlayerPrivacy'
import {PlayerMatchCards} from '../components/PlayerMatchCards'
import {releaseNotes, releaseNoteSections} from '../releaseNotes'
import {passcodeErrorMessage} from '../passcodeMessages'
import type {AppState, MatchTeam} from '../types'

afterEach(() => { void i18n.changeLanguage('en'); vi.unstubAllGlobals() })

const state: AppState = {
  locked: false, hasPasscode: true, pinMode: 'unlock', pinError: '', gameDetected: false,
  accounts: [], followed: [], searchHistory: [], currentMatch: {}, riotClient: {detected: false, label: 'Offline'},
  settings: {autoLockMinutes: 0, lockOnBlur: false, reduceMotion: true, riotApiConfigured: false, clipboardClearSeconds: 15},
}

describe('bundled localization', () => {
  it.each([
    [null, ['fr-CA'], 'fr'], [null, ['ko-KR'], 'ko'], [null, ['en-GB'], 'en'],
    [null, ['de-DE'], 'en'], [null, [], 'en'], [null, ['es-ES', 'fr-FR'], 'fr'],
    ['en', ['ko-KR'], 'en'], ['ko', ['fr-FR'], 'ko'], ['broken', ['fr-FR'], 'fr'],
  ] as const)('selects saved language %s before device preferences %j', (saved, preferred, expected) => {
    expect(detectLanguage(saved, preferred)).toBe(expected)
  })

  it('persists an explicit choice, updates document language and restores it on startup', () => {
    const values = new Map<string, string>()
    const storage = {getItem: (key: string) => values.get(key) ?? null, setItem: (key: string, value: string) => values.set(key, value)}
    const documentElement = {lang: '', dir: ''}
    vi.stubGlobal('window', {localStorage: storage})
    vi.stubGlobal('document', {documentElement})
    vi.stubGlobal('navigator', {language: 'fr-FR', languages: ['fr-FR']})
    initializeLanguage()
    expect(getLanguage()).toBe('fr')
    expect(values.has(LANGUAGE_STORAGE_KEY)).toBe(false)
    vi.stubGlobal('navigator', {language: 'ko-KR', languages: ['ko-KR']})
    initializeLanguage()
    expect(getLanguage()).toBe('ko')
    setLanguage('ko')
    expect(values.get(LANGUAGE_STORAGE_KEY)).toBe('ko')
    expect(documentElement).toEqual({lang: 'ko', dir: 'ltr'})
    void i18n.changeLanguage('en')
    vi.stubGlobal('navigator', {language: 'fr-FR', languages: ['fr-FR']})
    initializeLanguage()
    expect(getLanguage()).toBe('ko')
  })

  it('still works when local storage is blocked', () => {
    vi.stubGlobal('window', {get localStorage() { throw new Error('blocked') }})
    vi.stubGlobal('navigator', {language: 'ko-KR', languages: ['ko-KR']})
    expect(() => initializeLanguage()).not.toThrow()
    expect(getLanguage()).toBe('ko')
    expect(() => setLanguage('fr')).not.toThrow()
    expect(t('Accounts')).toBe('Comptes')
  })

  it('ships complete catalogs with identical interpolation fields and an English fallback', () => {
    const keys = Object.keys(en).sort()
    const fields = (value: string) => [...value.matchAll(/\{\{([^}]+)\}\}/g)].map(match => match[1]).sort()
    for (const catalog of [fr, ko]) {
      expect(Object.keys(catalog).sort()).toEqual(keys)
      for (const key of keys as Array<keyof typeof en>) {
        expect(catalog[key].trim(), key).not.toBe('')
        expect(fields(catalog[key]), key).toEqual(fields(en[key]))
      }
    }
    i18n.addResource('en', 'translation', 'test.englishFallback', 'Fallback copy')
    void i18n.changeLanguage('ko')
    expect(t('test.englishFallback')).toBe('Fallback copy')
    expect(t('Uncatalogued value')).toBe('Uncatalogued value')
  })

  it('keeps all entry-screen, destructive-reset and release copy in every catalog', () => {
    const copy = [ONBOARDING_ACTION, ONBOARDING_BODY, ONBOARDING_HEADING,
      ...Object.values(RESET_PROMPTS).flatMap(Object.values), releaseNotes.summary,
      ...releaseNoteSections.flatMap(section => [section.label, ...releaseNotes[section.key]])]
    for (const key of copy) expect(en, key).toHaveProperty(key)
    expect(releaseNoteSections.map(section => section.key)).toEqual(['added', 'fixed', 'changed', 'removed', 'knownIssues'])
  })

  it('handles plurals, number formatting and both long and abbreviated relative dates', () => {
    expect(t('{{count}} players', {count: 1})).toBe('1 player')
    expect(t('{{count}} players', {count: 2})).toBe('2 players')
    void i18n.changeLanguage('fr')
    expect(t('{{count}} watched players', {count: 1})).toBe('1 joueur suivi')
    expect(t('{{count}} watched players', {count: 3})).toBe('3 joueurs suivis')
    expect(displayText('42 min ago')).toBe('il y a 42 minutes')
    expect(displayText('3h ago')).toBe('il y a 3 heures')
    expect(displayText('2 days ago')).toBe('avant-hier')
    expect(formatNumber(1.25)).toBe('1,25')
    void i18n.changeLanguage('ko')
    expect(t('{{count}} players', {count: 1})).toBe('플레이어 1명')
    expect(displayText('Gold II')).toBe('골드 II')
    expect(displayText('42 min ago')).toBe('42분 전')
  })

  it.each([['en', 'Peaks is locked', 'Welcome to Peaks', 'Language'], ['fr', 'Peaks est verrouillé', 'Bienvenue sur Peaks', 'Langue'], ['ko', 'Peaks가 잠겨 있어요', 'Peaks에 오신 것을 환영해요', '언어']])('renders entry screens and Settings in %s', (language, locked, welcome, label) => {
    void i18n.changeLanguage(language)
    const render = (children: React.ReactNode) => renderToStaticMarkup(<LocaleProvider><LayerProvider>{children}</LayerProvider></LocaleProvider>)
    expect(render(<LockScreen mode="unlock" onReset={async () => undefined} onSubmit={async () => undefined} />)).toContain(locked)
    const onboarding = render(<OnboardingScreen onGetStarted={() => undefined} />)
    expect(onboarding).toContain(welcome)
    expect(onboarding).toContain(`>${label}</label>`)
    const settings = render(<SettingsScreen state={state} action={async () => undefined} />)
    expect(settings).toContain(`>${label}</label>`)
    for (const html of [onboarding, settings]) expect(html).toContain(language === 'ko' ? '한국어' : language === 'fr' ? 'Français' : 'English')
  })

  it('keeps Riot identities and canonical match data unchanged while translating cards and aliases', () => {
    void i18n.changeLanguage('ko')
    const teams: MatchTeam[] = [{name: 'Team 1', players: [{name: 'Example#EUW', self: true, currentRank: 'Gold 2', stats: {kills: 15, deaths: 8, assists: 3}}]}]
    const original = JSON.stringify(teams)
    const markup = renderToStaticMarkup(<LayerProvider><PlayerMatchCards teams={teams} game="VALORANT" label="Live" onSelectPlayer={() => undefined} /></LayerProvider>)
    expect(markup).toContain('Example#EUW')
    expect(markup).toContain('골드 2')
    expect(markup).toContain('어시스트')
    expect(JSON.stringify(teams)).toBe(original)
    function Identity() { const privacy = usePlayerPrivacy(); return <p>{privacy.displayName('Secret#ID')} {privacy.redact('Secret#ID')}</p> }
    const privateHtml = renderToStaticMarkup(<PlayerPrivacyProvider state={{...state, settings: {...state.settings, streamerMode: true}}}><Identity /></PlayerPrivacyProvider>)
    expect(privateHtml).toContain('플레이어 1')
    expect(privateHtml).not.toContain('Secret')
    void i18n.changeLanguage('fr')
    expect(displayText(passcodeErrorMessage(new Error("Error invoking remote method 'peaks:invoke': Error: That passcode was not recognized"), 'Could not check the password. Try again.'))).toBe('Le mot de passe n’est pas correct.')
  })
})
