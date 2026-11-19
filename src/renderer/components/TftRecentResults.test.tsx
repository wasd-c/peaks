import {LayerProvider} from '@astryxdesign/core/Layer'
import {renderToStaticMarkup} from 'react-dom/server'
import {describe, expect, it} from 'vitest'
import type {Account} from '../types'
import {TftRecentResults} from './TftRecentResults'

const account = (placements: number[]): Account => ({
  id: 'test-account', riotId: 'Owner#TEST', region: 'EUW', ranks: [],
  matches: placements.map((placement, index) => ({
    id: `tft-${index}`, game: 'Teamfight Tactics', result: 'Unknown', playedAtTimestamp: 1_735_689_600_000 - index * 60_000,
    teams: [{name: 'Lobby', players: [{name: 'Owner#TEST', self: true, stats: {placement}}]}],
  })),
})
const render = (placements: number[]) => renderToStaticMarkup(<LayerProvider><TftRecentResults account={account(placements)} onSelectMatch={() => undefined} /></LayerProvider>)

describe('TFT result strip', () => {
  it.each([
    [[1], 'none'], [[8], 'none'], [[1, 4], 'fire'], [[5, 8], 'frost'],
  ] as const)('starts the correct effect at the two-game threshold for %s', (placements, effect) => {
    const markup = render([...placements])
    expect(markup).toContain(`data-effect="${effect}"`)
    expect(markup.includes('pd-tft-streak__canvas')).toBe(effect === 'fire')
    expect(markup.includes('pd-tft-streak__effect pd-tft-streak__frost')).toBe(effect === 'frost')
  })

  it('keeps each visible button to the placement while exposing a dated accessible name', () => {
    const markup = render([1, 2, 5, 8])
    const buttons = [...markup.matchAll(/<button\b[^>]*\bdata-placement="[^"]+"[^>]*>([\s\S]*?)<\/button>/g)]
    expect(buttons).toHaveLength(4)
    expect(buttons.map(button => button[1].replace(/<[^>]+>/g, ''))).toEqual(['#1', '#2', '#5', '#8'])
    expect(markup).toMatch(/aria-label="#1 · [^"]+2025[^"]+View match"/)
    expect(markup).toContain('color:var(--color-tft-place-gold)')
    expect(markup).toContain('color:var(--color-tft-place-silver)')
    expect(markup).toContain('color:var(--color-tft-place-white)')
    expect(markup).toContain('data-metal="gold"')
    expect(markup).toContain('data-metal="silver"')
  })

  it('renders twenty real results across solo and Double Up by default', () => {
    const data = account(Array.from({length: 20}, (_, index) => index % 8 + 1))
    data.matches!.forEach((match, index) => { if (index % 4 === 0) match.teamMode = 'duos' })
    const markup = renderToStaticMarkup(<LayerProvider><TftRecentResults account={data} onSelectMatch={() => undefined} /></LayerProvider>)
    expect(markup.match(/\bdata-placement=/g)).toHaveLength(20)
    const filtered = renderToStaticMarkup(<LayerProvider><TftRecentResults account={data} mode="solo" onSelectMatch={() => undefined} /></LayerProvider>)
    expect(filtered.match(/\bdata-placement=/g)).toHaveLength(15)
  })
})
