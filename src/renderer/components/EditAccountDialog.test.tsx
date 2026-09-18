import {LayerProvider} from '@astryxdesign/core/Layer'
import {renderToStaticMarkup} from 'react-dom/server'
import {describe, expect, it} from 'vitest'
import {AccountIconPicker, EditAccountDialog} from './EditAccountDialog'
import {AccountSelectionTile} from './AccountSelectionTile'
import {PlayerPrivacyProvider} from './PlayerPrivacy'
import type {AppState} from '../types'

const state: AppState = {
  locked: false, hasPasscode: true, pinMode: 'unlock', pinError: '',
  accounts: [{id: 'private-account', riotId: 'PrivateOwner#SECRET', nickname: 'PrivateNickname', region: 'EUW', ranks: [],
    accountIcon: {game: 'League of Legends', characterId: 'Ahri'},
  }],
  followed: [], searchHistory: [], currentMatch: {}, gameDetected: false,
  settings: {autoLockMinutes: 0, lockOnBlur: false, streamerMode: true, reduceMotion: true,
    riotApiConfigured: false, clipboardClearSeconds: 15},
  riotClient: {detected: false, label: 'Offline'},
}

describe('account icon editor privacy', () => {
  it('redacts visible and accessible account identity while preserving character selection', () => {
    const render = (privateMode: boolean) => renderToStaticMarkup(<LayerProvider>
      <PlayerPrivacyProvider state={{...state, settings: {...state.settings, streamerMode: privateMode}}}>
        <EditAccountDialog account={state.accounts[0]} onClose={() => undefined}
          onSave={async () => undefined} onDelete={async () => undefined} />
      </PlayerPrivacyProvider>
    </LayerProvider>)
    const privateHtml = render(true)
    expect(privateHtml).not.toContain('PrivateOwner')
    expect(privateHtml).not.toContain('SECRET')
    expect(privateHtml).toContain('Player 1')
    expect(privateHtml).not.toContain('PrivateNickname')
    expect(privateHtml).not.toContain('Nickname')
    const normalHtml = render(false)
    expect(normalHtml).toContain('PrivateOwner#SECRET')
    expect(normalHtml).toContain('value="PrivateNickname"')
    expect(normalHtml).toContain('Choose an icon')
    expect(normalHtml).not.toContain('Automatic icon')
    expect(normalHtml).not.toContain('Search characters')
    expect(normalHtml).not.toContain('pd-account-picker__character')
  })

  it('keeps the character grid behind its own picker, with both game choices and a reset option', () => {
    const html = renderToStaticMarkup(<LayerProvider>
      <AccountIconPicker selection={state.accounts[0].accountIcon ?? null} initialGame="League of Legends"
        onSelect={() => undefined} onClose={() => undefined} />
    </LayerProvider>)
    expect(html).toContain('data-columns="4"')
    expect(html).toContain('Search characters')
    expect(html).toContain('League of Legends')
    expect(html).toContain('VALORANT')
    expect(html).toContain('Use latest character')
    expect(html).toContain('Ahri')
    expect(html).not.toContain('PrivateOwner')
    expect(html).not.toContain('PrivateNickname')
  })

  const tile = (privateMode: boolean, phase?: 'pending' | 'approved' | 'leaving') => renderToStaticMarkup(
    <LayerProvider><PlayerPrivacyProvider state={{...state, settings: {...state.settings, streamerMode: privateMode}}}>
      <AccountSelectionTile account={state.accounts[0]} isBusy={Boolean(phase)} phase={phase}
        onUse={() => undefined} onEdit={() => undefined} onSelect={() => undefined} />
    </PlayerPrivacyProvider></LayerProvider>,
  )

  it('shows the nickname on the tile while retaining the Riot ID, and hides both under Streamer Mode', () => {
    const normalHtml = tile(false)
    expect(normalHtml).toContain('>PrivateNickname</')
    expect(normalHtml).toContain('>PrivateOwner#SECRET</')
    const privateHtml = tile(true)
    expect(privateHtml).toContain('Player 1')
    expect(privateHtml).not.toContain('PrivateNickname')
    expect(privateHtml).not.toContain('PrivateOwner')
    expect(privateHtml).not.toContain('SECRET')
  })

  it.each(['approved', 'leaving'] as const)('shows only a check after approval in %s, with an accessible status', phase => {
    const html = tile(false, phase)
    expect(html).toContain('pd-account-tile__check')
    expect(html).toContain('aria-label="Approved by Riot"')
    expect(html).not.toMatch(/>Approved by Riot</)
    expect(html).not.toContain('Connecting…')
  })

  it('keeps a visible pending message while waiting for Riot', () => {
    const html = tile(false, 'pending')
    expect(html).toContain('Connecting…')
    expect(html).not.toContain('pd-account-tile__check')
  })
})
