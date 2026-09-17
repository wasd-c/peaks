import type {ReactNode} from 'react'
import {renderToStaticMarkup} from 'react-dom/server'
import {LayerProvider} from '@astryxdesign/core/Layer'
import {describe, expect, it} from 'vitest'
import {PlayerAliases} from './privacy'
import {PlayerPrivacyProvider} from './components/PlayerPrivacy'
import {MatchStandouts} from './components/MatchInsights'
import {CurrentMatchScreen} from './screens/CurrentMatchScreen'
import {MatchDetailScreen} from './screens/MatchDetailScreen'
import {OverviewScreen} from './screens/OverviewScreen'
import {SearchScreen} from './screens/SearchScreen'
import {PlayerProfileScreen} from './screens/PlayerProfileScreen'
import {AccountDetailScreen} from './screens/AccountDetailScreen'
import {SettingsScreen} from './screens/SettingsScreen'
import {PlayerList} from './screens/shared'
import {matchShareSummary} from './matchShare'
import type {AppState, Match} from './types'

const noop = () => undefined
const action = async () => undefined
const match: Match = {
  id: 'match-1', game: 'VALORANT', result: 'Win', map: 'Ascent',
  teams: [{name: 'Your team', players: [
    {name: 'SecretOwner', riotId: 'SecretOwner#A01', agent: 'Omen', self: true, stats: {kills: 20, deaths: 10, assists: 5}},
    {name: 'SecretRival', riotId: 'SecretRival#A02', agent: 'Sova', stats: {kills: 22, deaths: 11, assists: 4, headshots: 15, bodyshots: 20, legshots: 0}},
  ]}],
}
const state: AppState = {
  locked: false, hasPasscode: true, pinMode: 'unlock', pinError: '',
  accounts: [{id: 'owned-1', riotId: 'SecretOwner#A01', region: 'EUW', connected: true, ranks: [], matches: [match]}],
  followed: [{id: 'followed-1', riotId: 'SecretFriend#A03', region: 'EUW', matches: [match]}],
  searchHistory: ['SecretFriend#A03'],
  currentMatch: {game: 'VALORANT', map: 'Ascent', teams: match.teams},
  gameDetected: true,
  settings: {autoLockMinutes: 0, lockOnBlur: false, streamerMode: true, reduceMotion: true, riotApiConfigured: false, clipboardClearSeconds: 15},
  riotClient: {detected: true, label: 'VALORANT'},
}

const render = (children: ReactNode, enabled = true) => renderToStaticMarkup(
  <LayerProvider>
    <PlayerPrivacyProvider state={{...state, settings: {...state.settings, streamerMode: enabled}}}>
      {children}
    </PlayerPrivacyProvider>
  </LayerProvider>,
)

describe('Streamer Mode', () => {
  const screens: Array<[string, ReactNode]> = [
    ['accounts', <OverviewScreen state={state} view="list" onView={noop} onSelect={noop} onAdd={noop} />],
    ['account details', <AccountDetailScreen account={state.accounts[0]} onBack={noop} onCopy={noop} onConnect={noop} onDelete={noop} onPasteQr={action} onRefresh={noop} onSelectMatch={noop} />],
    ['player profile', <PlayerProfileScreen player={state.followed[0]} onBack={noop} onSelectMatch={noop} />],
    ['watchlist', <PlayerList players={state.followed} heading="Players" action={action} />],
    ['search history', <SearchScreen state={state} action={action} invoke={async <T,>() => [] as T} onSelectPlayer={noop} />],
    ['live match', <CurrentMatchScreen state={state} onSelectPlayer={noop} />],
    ['match report', <MatchDetailScreen match={match} onBack={noop} onSelectPlayer={noop} />],
    ['standout players', <MatchStandouts match={match} riotId={state.accounts[0].riotId} />],
  ]

  it.each(screens)('hides real identities and accessible labels in %s', (_name, screen) => {
    const original = JSON.stringify(state)
    const html = render(screen)
    expect(html).toMatch(/Player [1-9]/)
    for (const name of ['SecretOwner', 'SecretRival', 'SecretFriend']) expect(html).not.toContain(name)
    expect(JSON.stringify(state)).toBe(original)
    expect(render(screen, false)).toMatch(/SecretOwner|SecretRival|SecretFriend/)
  })

  it('keeps stable aliases across reordered names and different casing', () => {
    const aliases = new PlayerAliases()
    expect(aliases.name('Name.*#TAG')).toBe('Player 1')
    expect(aliases.name('Other#TAG')).toBe('Player 2')
    expect(aliases.name(' name.*#tag ')).toBe('Player 1')
    expect(aliases.redact('Connected Name.*#TAG; Other#TAG disconnected.'))
      .toBe('Connected Player 1; Player 2 disconnected.')
  })

  it('anonymizes exported posters while resolving the real owner and their statistics', () => {
    const aliases = new PlayerAliases()
    aliases.seed(state)
    const summary = matchShareSummary(match, state.accounts[0], name => aliases.name(name))
    expect(summary.playerName).toBe('Player 1')
    expect(summary.kda).toBe('20 / 10 / 5')
    expect(JSON.stringify(summary)).not.toContain('SecretOwner')
  })

  it('offers all three preferences and masks Riot ID search input', () => {
    const settings = render(<SettingsScreen state={state} action={action} />)
    expect(settings).toContain('Only when Peaks closes')
    expect(settings).toContain('Streamer Mode')
    expect(settings).toContain('Change security code')
    const search = render(screens[4][1])
    expect(search).toContain('type="password"')
  })
})
