import {LayerProvider} from '@astryxdesign/core/Layer'
import {renderToStaticMarkup} from 'react-dom/server'
import {afterEach, describe, expect, it, vi} from 'vitest'
import {timelineStart, TIMELINE_HOUR} from '../activityTimeline'
import {getLanguage, localeTags} from '../i18n'
import {DayTimeline, TimelineMarkers} from './ActivityCalendar'

afterEach(() => vi.useRealTimers())

describe('timeline guide presentation', () => {
  it('renders a blue current-time guide and dated white midnight guides with edge-safe label anchors', () => {
    const start = timelineStart('2026-09-20'), now = start + 12.5 * TIMELINE_HOUR
    const html = renderToStaticMarkup(<TimelineMarkers start={start} now={now} />)
    expect((html.match(/data-timeline-marker="midnight"/g) ?? [])).toHaveLength(2)
    expect((html.match(/data-timeline-marker="now"/g) ?? [])).toHaveLength(1)
    expect(html).toContain('pd-day-timeline__marker--now')
    expect(html).toContain('pd-day-timeline__marker--midnight')
    expect(html).toContain('data-label-edge="start"')
    expect(html).toContain('data-label-edge="end"')
    for (const timestamp of [start, start + 24 * TIMELINE_HOUR]) {
      expect(html).toContain(new Date(timestamp).toISOString())
      expect(html).toContain(new Intl.DateTimeFormat(localeTags[getLanguage()], {dateStyle: 'medium'}).format(timestamp))
    }
    expect(html).toContain(new Date(now).toISOString())
  })

  it('includes the current-time guide in the actual day view without adding interactive controls over games', () => {
    const start = timelineStart('2026-09-20')
    vi.useFakeTimers().setSystemTime(start + 7 * TIMELINE_HOUR)
    const html = renderToStaticMarkup(<LayerProvider><DayTimeline date="2026-09-20" matches={[]} onSelectMatch={() => undefined} onClose={() => undefined} /></LayerProvider>)
    expect(html).toContain('data-timeline-marker="now"')
    expect((html.match(/role="group"/g) ?? [])).toHaveLength(3)
    const markers = renderToStaticMarkup(<TimelineMarkers start={start} now={Date.now()} />)
    expect(markers).toContain('aria-hidden="true"')
    expect(markers).not.toMatch(/<(?:button|a)\b/)
    expect(markers).not.toContain('tabindex')
  })

  it('omits the current-time guide when browsing a past window but retains its midnight dates', () => {
    const start = timelineStart('2026-09-20')
    const html = renderToStaticMarkup(<TimelineMarkers start={start} now={start + 48 * TIMELINE_HOUR} />)
    expect(html).not.toContain('data-timeline-marker="now"')
    expect((html.match(/data-timeline-marker="midnight"/g) ?? [])).toHaveLength(2)
  })
})
