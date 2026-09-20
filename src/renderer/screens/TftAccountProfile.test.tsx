import {LayerProvider} from '@astryxdesign/core/Layer'
import {renderToStaticMarkup} from 'react-dom/server'
import {describe, expect, it} from 'vitest'
import type {TftComposition} from '../types'
import {TftBoard} from './TftAccountProfile'

const render = (composition: TftComposition) => renderToStaticMarkup(<LayerProvider><TftBoard composition={composition} /></LayerProvider>)

describe('TFT composition upgrade and item markers', () => {
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
