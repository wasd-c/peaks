import {LayerProvider} from '../ui'
import {renderToStaticMarkup} from 'react-dom/server'
import {describe, expect, it} from 'vitest'
import type {Account, TftComposition} from '../types'
import {TftAccountProfile, TftBoard} from './TftAccountProfile'

const render = (composition: TftComposition) => renderToStaticMarkup(<LayerProvider><TftBoard composition={composition} /></LayerProvider>)

describe('TFT composition upgrade and item markers', () => {
  it('orders stars before cost and preserves the original board data', () => {
    const composition = {setNumber: 17, units: [
      {id: 'TFT17_Fiora', stars: 1}, {id: 'TFT17_Briar', stars: 3},
      {id: 'TFT17_Fiora', stars: 2}, {id: 'TFT17_Briar', stars: 2},
    ]}
    const original = structuredClone(composition)
    const html = render(composition)
    const labels = [...html.matchAll(/role="listitem" aria-label="([^"]+)"/g)].map(match => match[1])
    expect(labels).toEqual(['Briar, 3 stars', 'Fiora, 2 stars', 'Briar, 2 stars', 'Fiora, 1 stars'])
    expect(composition).toEqual(original)
  })

  it.each([undefined, 0, 143])('hides missing damage but keeps a recorded value of %s', damage => {
    const account: Account = {id: 'owner', riotId: 'Owner#TEST', region: 'EUW', ranks: [], matches: [
      {id: 'match', game: 'Teamfight Tactics', result: 'Win', teams: [{name: 'Lobby', players: [{name: 'Owner#TEST', stats: {placement: 1, damage}}]}]},
    ]}
    const html = renderToStaticMarkup(<LayerProvider><TftAccountProfile account={account} isSynchronizing={false} onSelectMatch={() => undefined} /></LayerProvider>)
    expect(html.includes('Damage to players')).toBe(damage != null)
  })
  it.each([[1, 'bronze'], [2, 'silver'], [3, 'gold'], [4, 'gold']] as const)('preserves %i stars with the correct metal and an accessible unit label', (stars, metal) => {
    const markup = render({units: [{id: 'DA_Sentinel18', stars}]})
    expect(markup).toContain(`data-stars="${stars}" data-metal="${metal}"`)
    expect(markup.match(/class="pd-tft-unit__star"/g)).toHaveLength(stars)
    expect(markup).toContain(`${stars} stars`)
    expect(markup).toContain('data-cost="4"')
    expect(markup).toContain('var(--color-tft-cost-4)')
    expect(markup).toContain('DA_Sentinel18.png')
  })

  it('keeps all three equipped items attached to the portrait with their own accessible identities', () => {
    const markup = render({units: [{id: 'DA_Sentinel18', stars: 3, items: ['TFT_Item_InfinityEdge', 'TFT_Item_GuinsoosRageblade', 'TFT_Item_Bloodthirster']}]})
    expect(markup).toContain('pd-tft-unit__items')
    expect(markup).toContain('aria-label="Equipped items"')
    expect(markup.match(/pd-tft-icon--small/g)).toHaveLength(3)
    expect(markup).toContain('Infinity Edge')
    expect(markup).toContain('Guinsoo')
    expect(markup).toContain('Bloodthirster')
  })

  it('keeps unknown unit and item identities explicit without inventing a portrait or upgrade', () => {
    const markup = render({units: [{id: 'TFT999_Unknown', stars: 0, items: ['TFT999_Item']}]})
    expect(markup).toContain('TFT999_Unknown')
    expect(markup).toContain('TFT999_Item')
    expect(markup).toContain('pd-tft-icon--champion')
    expect(markup).not.toContain('pd-tft-unit__stars')
  })
})
