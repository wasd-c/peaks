import {renderToStaticMarkup} from 'react-dom/server'
import {LayerProvider} from '../ui'
import {describe, expect, it} from 'vitest'
import {PlayerPrivacyProvider} from '../components/PlayerPrivacy'
import type {AppState, Game} from '../types'
import {OverviewScreen} from './OverviewScreen'
import {WatchlistScreen} from './FollowedScreen'

const games: Game[] = ['VALORANT', 'League of Legends', 'Teamfight Tactics']
const state: AppState = {
  locked: false, hasPasscode: true, pinMode: 'unlock', pinError: '',
  accounts: games.map((game, index) => ({id: `account-${index}`, riotId: `Account${index}#TEST`, region: 'EUW', ranks: [{game, tier: 'Unranked'}]})),
  followed: games.map((game, index) => ({id: `player-${index}`, riotId: `Watched${index}#TEST`, region: 'EUW', game})),
  searchHistory: [], currentMatch: {}, gameDetected: false,
  settings: {autoLockMinutes: 0, lockOnBlur: false, streamerMode: false, reduceMotion: true, riotApiConfigured: false, clipboardClearSeconds: 15},
  riotClient: {detected: false, label: 'Offline'},
}
const noop = () => undefined

describe('account and watched-player collections', () => {
  it('renders a real table, defaults to recent connections and keeps icon and actions unsortable', () => {
    const tableState = {...state, accounts: state.accounts.map((account, index) => ({...account, nickname: index === 1 ? 'My account' : undefined, lastConnectedAt: index === 1 ? Date.UTC(2026, 8, 21) : undefined}))}
    const html = renderToStaticMarkup(<LayerProvider><PlayerPrivacyProvider state={tableState}>
      <OverviewScreen state={tableState} view="list" onView={noop} onSelect={noop} onAdd={noop} onUse={noop} onEdit={noop} />
    </PlayerPrivacyProvider></LayerProvider>)
    expect(html).toContain('<table')
    const headers = html.match(/<thead[\s\S]*?<\/thead>/)?.[0] ?? ''
    expect(headers).toContain('Name')
    expect(headers).toContain('Last connection date')
    expect(headers.match(/ant-table-column-has-sorters/g)).toHaveLength(2)
    expect(headers).not.toContain('Icon')
    const body = html.match(/<tbody[\s\S]*?<\/tbody>/)?.[0] ?? ''
    expect(body.indexOf('My account')).toBeLessThan(body.indexOf('Account0'))
    expect(body).toContain('Not recorded')
    expect(body).toContain('Use')
    expect(body).toContain('Edit')
  })
  it('shows accounts from every game without a game selector', () => {
    const html = renderToStaticMarkup(<LayerProvider><PlayerPrivacyProvider state={state}>
      <OverviewScreen state={state} view="grid" onView={noop} onSelect={noop} onAdd={noop} onUse={noop} onEdit={noop} />
    </PlayerPrivacyProvider></LayerProvider>)
    state.accounts.forEach(account => expect(html).toContain(account.riotId))
    expect(html).toContain('Find an account')
    expect(html).not.toContain('All games')
    expect(html).not.toContain('role="tab"')
  })

  it('keeps all watched players available without a game picker', () => {
    const html = renderToStaticMarkup(<LayerProvider><PlayerPrivacyProvider state={state}>
      <WatchlistScreen state={state} action={async () => undefined} onSelectPlayer={noop} />
    </PlayerPrivacyProvider></LayerProvider>)
    state.followed.forEach(player => expect(html).toContain(player.riotId))
    expect(html).toContain('Filter watched players')
    expect(html).not.toContain('Filter by game')
    expect(html).not.toContain('role="combobox"')
  })
})
