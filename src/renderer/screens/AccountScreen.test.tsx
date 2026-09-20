import {renderToStaticMarkup} from 'react-dom/server'
import {LayerProvider} from '@astryxdesign/core/Layer'
import {describe, expect, it} from 'vitest'
import {PlayerPrivacyProvider} from '../components/PlayerPrivacy'
import type {Account, AppState} from '../types'
import {AccountScreen, ProfileHero} from './AccountScreen'
import {ValorantAccountProfile} from './ValorantAccountProfile'

const account: Account = {id: 'opaque', riotId: 'PrivateName#TEST', region: 'EUW', valorantRegion: 'EU', level: 900,
  ranks: [{game: 'VALORANT', tier: 'Ascendant', division: '3', rating: 70, peakTier: 'Immortal', peakDivision: '1', peakSeason: 'E7:A3'}],
  matches: [{id: 'one', game: 'VALORANT', mode: 'competitive', map: 'Ascent', result: 'Win', teams: [{name: 'Blue', players: [{name: 'PrivateName#TEST', self: true, stats: {kills: 20, deaths: 10, assists: 5}}]}]}],
}
const noop = () => undefined
function page(streamerMode = false, game: 'riot' | 'VALORANT' = 'VALORANT') {
  const state = {accounts: [account], followed: [], searchHistory: [], currentMatch: {}, settings: {streamerMode}} as unknown as AppState
  return renderToStaticMarkup(<LayerProvider><PlayerPrivacyProvider state={state}>
    {game === 'riot' ? <AccountScreen account={account} isActive onRefresh={async () => undefined} onSelectMatch={noop} onManage={noop} onAdd={noop} />
      : <><ProfileHero account={account} game={game} isActive /><ValorantAccountProfile account={account} onSelectMatch={noop} /></>}
  </PlayerPrivacyProvider></LayerProvider>)
}

describe('account profile presentation', () => {
  it('opens on a neutral Riot profile and offers all three games including games without data', () => {
    const html = page(true, 'riot')
    expect(html).toContain('data-profile-game="riot"')
    expect(html).toContain('aria-label="VALORANT"')
    expect(html).toContain('aria-label="League of Legends"')
    expect(html).toContain('aria-label="Teamfight Tactics"')
    expect(html).not.toContain('Damage / round')
    expect(html).not.toContain('PrivateName')
  })
  it('preserves privacy and does not substitute League level or invented peak RR', () => {
    const html = page(true)
    expect(html).not.toContain('PrivateName')
    expect(html).not.toContain('#TEST')
    expect(html).not.toContain('900')
    expect(html).toContain('E7:A3')
    expect(html).toContain('Immortal 1')
    expect(html).not.toContain('>0 RR<')
  })
  it('renders absent damage and round events as unavailable while keeping known KDA', () => {
    const html = page()
    expect(html).toContain('PrivateName#TEST')
    expect(html).toContain('Damage / round')
    expect(html).toContain('—')
    expect(html).not.toContain('>0%<')
    expect(html).not.toContain('role="progressbar"')
  })
})
