import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest'
import {matchShareSummary, type MatchShareSummary} from './matchShare'
import {renderMatchPoster} from './matchPoster'

vi.mock('./assets', () => ({
  gameArtwork: () => 'map-art',
  valorantMapName: (map: string) => map,
  valorantAgentName: (agent?: string) => agent,
  valorantAgentPortraitAsset: (agent?: string) => agent ? 'standing-agent' : undefined,
}))

const summary: MatchShareSummary = {
  game: 'VALORANT', result: 'Win', map: 'Haven', mode: 'Competitive', score: '13 : 9',
  duration: '38m', playerName: 'Player 1', character: 'Waylay',
  kda: '24 / 15 / 4', combatScore: '267', damagePerRound: '213',
  tags: [{label: 'Raid boss', source: 'match'}, {label: 'Walking orb 🥀', source: 'history'}],
}

function canvasHarness(failImages = false, failExport = false) {
  const context = {
    fillRect: vi.fn(), drawImage: vi.fn(), fillText: vi.fn(), beginPath: vi.fn(),
    moveTo: vi.fn(), lineTo: vi.fn(), closePath: vi.fn(), fill: vi.fn(), save: vi.fn(), restore: vi.fn(),
    arc: vi.fn(), clip: vi.fn(), translate: vi.fn(), rotate: vi.fn(), stroke: vi.fn(),
    strokeRect: vi.fn(), strokeText: vi.fn(), setLineDash: vi.fn(),
    createLinearGradient: vi.fn(() => ({addColorStop: vi.fn()})),
    createRadialGradient: vi.fn(() => ({addColorStop: vi.fn()})),
    measureText: (text: string) => ({width: text.length * 12}),
    getImageData: () => ({data: new Uint8ClampedArray(16 * 16 * 4).fill(255)}),
  }
  const canvases: Array<{width: number; height: number}> = []
  const theme = {appendChild: vi.fn()}
  vi.stubGlobal('document', {
    querySelector: () => theme, documentElement: theme, fonts: {ready: Promise.resolve()},
    createElement: () => {
      const canvas = {width: 0, height: 0, style: {}, remove: vi.fn(),
        getContext: () => context,
        toBlob: (callback: (blob: Blob | null) => void) => callback(failExport ? null : new Blob(['png'], {type: 'image/png'})),
      }
      canvases.push(canvas)
      return canvas
    },
  })
  vi.stubGlobal('getComputedStyle', () => ({
    color: 'rgb(240, 240, 240)', fontFamily: 'sans-serif', getPropertyValue: () => 'sans-serif',
  }))
  vi.stubGlobal('Image', class {
    naturalWidth = 16
    naturalHeight = 16
    onload?: () => void
    onerror?: () => void
    source = ''
    set src(value: string) {
      this.source = value
      queueMicrotask(() => failImages ? this.onerror?.() : this.onload?.())
    }
  })
  return {context, canvases, text: () => context.fillText.mock.calls.map(call => call[0])}
}

beforeEach(() => vi.clearAllMocks())
afterEach(() => vi.unstubAllGlobals())

describe('match poster export', () => {
  it('renders the selected performance and standing agent into a widescreen PNG', async () => {
    const harness = canvasHarness()
    const blob = await renderMatchPoster(summary)
    expect(blob.type).toBe('image/png')
    expect(harness.canvases[0]).toMatchObject({width: 1600, height: 900})
    expect(harness.text()).toEqual(expect.arrayContaining(['PEAKS', 'VICTORY', '13 — 9', 'Player 1', '24 / 15 / 4', '267', '213', 'WAYLAY']))
    expect(harness.text()).toContain('COMPETITIVE / HAVEN')
    expect(harness.text()).toContain('Raid boss')
    expect(harness.text()).toContain('Walking orb 🥀')
    expect(harness.context.drawImage.mock.calls.some(call => call[0].source === 'standing-agent' && call.length === 9)).toBe(true)
  })

  it('exports timeless results even when the match is dated with a relative label', async () => {
    const harness = canvasHarness()
    await renderMatchPoster(matchShareSummary({game: 'VALORANT', result: 'Win', mode: 'Competitive',
      map: 'Abyss', playedAt: '42 minutes ago', duration: '34:12', teams: []}))
    expect(harness.text()).toContain('COMPETITIVE / ABYSS')
    expect(harness.text().join(' ')).not.toMatch(/MATCH RECEIPT|34:12/)
    expect(harness.text().join(' ')).not.toMatch(/ago|minutes|42/)
  })

  it('still exports factual text when local artwork fails to decode', async () => {
    const harness = canvasHarness(true)
    await renderMatchPoster({...summary, result: 'Loss'})
    expect(harness.context.drawImage).not.toHaveBeenCalled()
    expect(harness.text()).toContain('DEFEAT')
    expect(harness.text()).toContain('24 / 15 / 4')
  })

  it('does not invent missing metrics or reveal a hidden player through their portrait', async () => {
    const harness = canvasHarness()
    const privateSummary = matchShareSummary({game: 'VALORANT', result: 'Draw', teams: [
      {name: 'Team', players: [{name: 'Secret#ID', self: true, hidden: true, agent: 'Waylay', stats: {kills: 24}}]},
    ]})
    await renderMatchPoster(privateSummary)
    expect(harness.text()).toContain('DRAW')
    expect(harness.text().join(' ')).not.toMatch(/Secret|WAYLAY|KILLS|COMBAT SCORE|DAMAGE/)
    expect(harness.context.drawImage.mock.calls.some(call => call[0].source === 'standing-agent')).toBe(false)
  })

  it('rejects failed PNG encoding so the dialog can offer a retry', async () => {
    canvasHarness(false, true)
    await expect(renderMatchPoster(summary)).rejects.toThrow('PNG could not be exported')
  })
})
