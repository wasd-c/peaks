import {LayerProvider} from '../ui'
import {renderToStaticMarkup} from 'react-dom/server'
import {afterEach, beforeEach, describe, expect, it} from 'vitest'
import {emptyActivity} from '../activityAnalytics'
import {getLanguage, setLanguage} from '../i18n'
import {RiotActivity} from './RiotActivity'

const initialLanguage = getLanguage()
beforeEach(() => setLanguage('en'))
afterEach(() => setLanguage(initialLanguage))

describe('activity chart accessibility', () => {
  it('exposes every hour with one initial Tab stop, including hours with no playtime', () => {
    const html = renderToStaticMarkup(<LayerProvider><RiotActivity activity={emptyActivity()} /></LayerProvider>)
    const cells = html.match(/<[^>]*role="gridcell"[^>]*>/g) ?? []
    expect(cells).toHaveLength(168)
    expect(cells.filter(cell => cell.includes('tabindex="0"'))).toHaveLength(1)
    expect(cells.filter(cell => cell.includes('tabindex="-1"'))).toHaveLength(167)
    expect(cells[0]).toContain('aria-label="Mon · 0:00–1:00 · 0h 00m"')
    expect(cells.at(-1)).toContain('aria-label="Sun · 23:00–24:00 · 0h 00m"')
    expect(html).toContain('role="grid"')
    expect(html).toContain('aria-readonly="true"')
    expect(html).toContain('Use arrow keys to explore hours. Home and End move within a day.')
  })

  it('describes all session buckets and preserves exact hourly values for a recorded session', () => {
    const activity = emptyActivity([{id: 'session', game: 'VALORANT', map: 'Ascent', mode: 'Competitive', result: 'Win', playedAtTimestamp: new Date(2026, 0, 5, 12).getTime(), durationSeconds: 5400}])
    const html = renderToStaticMarkup(<LayerProvider><RiotActivity activity={activity} /></LayerProvider>)
    const histogram = html.match(/<svg\b[^>]*class="pd-activity-histogram"[^>]*>[\s\S]*?<\/svg>/)?.[0] ?? ''
    const description = histogram.match(/<desc id="([^"]+)">([^<]*)<\/desc>/)
    expect(description).not.toBeNull()
    expect(histogram).toContain(`aria-describedby="${description?.[1]}"`)
    expect(description?.[2]).toBe('&lt; 1h · Sessions: 0; 1–2h · Sessions: 1; 2–3h · Sessions: 0; 3–4h · Sessions: 0; 4–5h · Sessions: 0; 5–6h · Sessions: 0; 6h+ · Sessions: 0')
    expect(html).toContain('aria-label="Mon · 12:00–13:00 · 1h 00m"')
    expect(html).toContain('aria-label="Mon · 13:00–14:00 · 0h 30m"')
  })
})
