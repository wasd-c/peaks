import {renderToStaticMarkup} from 'react-dom/server'
import {LayerProvider} from '@astryxdesign/core/Layer'
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
  it('shows accounts from every game without a game selector', () => {
    const html = renderToStaticMarkup(<LayerProvider><PlayerPrivacyProvider state={state}>
      <OverviewScreen state={state} view="grid" onView={noop} onSelect={noop} onAdd={noop} />
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
