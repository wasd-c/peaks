import {renderToStaticMarkup} from 'react-dom/server'
import {LayerProvider} from '@astryxdesign/core/Layer'
import {describe, expect, it} from 'vitest'
import type {Player} from '../types'
import {rankAsset} from '../assets'
import {PlayerProfileScreen} from './PlayerProfileScreen'
import {PlayerList, rankColor, rankLabel, rankScore} from './shared'

const noop = () => undefined
const identity: Player = {id: 'player-1', riotId: 'Example#EUW', region: 'EUW', games: []}
const views = [
  ['player list', (player: Player) => <PlayerList action={async () => undefined} heading="Players" players={[player]} onSelect={noop} />],
  ['player profile', (player: Player) => <PlayerProfileScreen player={player} onBack={noop} onSelectMatch={noop} />],
] as const

describe.each(views)('%s rank presentation', (_name, view) => {
  const render = (player: Player) => renderToStaticMarkup(<LayerProvider>{view(player)}</LayerProvider>)

  it('shows every native game rank, exact division, local emblem and rating', () => {
    const html = render({...identity, currentRank: 'Stale rank', peakRank: 'Stale peak', ranks: [
      {game: 'League of Legends', tier: 'Gold III', rating: 68},
      {game: 'Teamfight Tactics', tier: 'Diamond II', rating: 0},
      {game: 'VALORANT', tier: 'Ascendant 2', rating: 45},
    ]})
    for (const value of ['League of Legends', 'Teamfight Tactics', 'VALORANT', 'Gold III', 'Diamond II', 'Ascendant 2', '68 LP', '0 LP', '45 RR']) {
      expect(html).toContain(value)
    }
    expect(html).toContain(rankAsset('League of Legends', 'Gold III'))
    expect(html).toContain(rankAsset('Teamfight Tactics', 'Diamond II'))
    expect(html).toContain(rankAsset('VALORANT', 'Ascendant 2'))
    expect(html).not.toContain('Stale rank')
    expect(html).not.toContain('Stale peak')
    expect(html).not.toContain('Rank unavailable')
  })

  it('does not manufacture a rank, game or rating for an identity-only result', () => {
    const html = render({...identity, ranks: []})
    expect(html).toContain('Rank unavailable')
    expect(html).not.toContain('Unranked')
    expect(html).not.toContain('VALORANT')
    expect(html).not.toContain('background-image')
    expect(html).not.toMatch(/\b0 (?:LP|RR)\b/)
  })

  it('keeps known contextual VALORANT current and peak ranks without a native rank list', () => {
    const html = render({...identity, game: 'VALORANT', currentRank: 'Ascendant 2', peakRank: 'Immortal 1'})
    expect(html).toContain('Ascendant 2')
    expect(html).toContain('Immortal 1')
    expect(html).not.toContain('Rank unavailable')
  })

  it('distinguishes an explicit unranked result from a missing rating', () => {
    const html = render({...identity, ranks: [{game: 'Teamfight Tactics', tier: 'Unranked'}]})
    expect(html).toContain('Teamfight Tactics')
    expect(html).toContain('Unranked')
    expect(html).not.toContain('Rank unavailable')
    expect(html).not.toMatch(/\b0 (?:LP|RR)\b/)
  })

  it('treats empty rank evidence as unavailable', () => {
    const html = render({...identity, currentRank: ' ', peakRank: '', ranks: [{game: 'Teamfight Tactics', tier: ''}]})
    expect(html).toContain('Rank unavailable')
    expect(html).not.toContain('Unranked')
  })
})

describe('rank labels', () => {
  it('orders and colors combined tiers like their canonical equivalents', () => {
    expect(rankScore({game: 'Teamfight Tactics', tier: 'Gold III'})).toBe(rankScore({game: 'Teamfight Tactics', tier: 'gold', division: 'III'}))
    expect(rankColor({game: 'Teamfight Tactics', tier: 'Gold III'})).toBe('yellow')
  })
  it('preserves canonical and separately supplied Roman divisions', () => {
    expect(rankLabel({game: 'League of Legends', tier: 'GOLD III'})).toBe('Gold III')
    expect(rankLabel({game: 'Teamfight Tactics', tier: 'diamond', division: 'iv'})).toBe('Diamond IV')
  })
})
