import {LayerProvider} from '../ui'
import {renderToStaticMarkup} from 'react-dom/server'
import {afterEach, beforeEach, describe, expect, it} from 'vitest'
import {getLanguage, setLanguage} from '../i18n'
import type {Match, ProfileActivity} from '../types'
import {DayTimeline} from './ActivityCalendar'
import {RankHistoryChart} from './RankHistoryChart'

const match: Match = {id: 'cached-match', game: 'VALORANT', map: 'Canyon', mode: 'Swiftplay', result: 'Win',
  playedAtTimestamp: new Date(2026, 8, 20, 6, 26).getTime(), durationSeconds: 600}
const noop = () => undefined
const initialLanguage = getLanguage()
beforeEach(() => setLanguage('fr'))
afterEach(() => setLanguage(initialLanguage))

describe('human-readable VALORANT activity labels', () => {
  it('uses the map name in calendar blocks and their tooltip while retaining mode and exact times', () => {
    const html = renderToStaticMarkup(<LayerProvider><DayTimeline date="2026-09-20" matches={[match]} onSelectMatch={noop} onClose={noop} /></LayerProvider>)
    expect(html).toContain('Fracture · Vélocité')
    expect(html).toContain('06:26–06:36')
    expect(html).not.toContain('Canyon')
  })

  it('resolves cached internal map paths in RR graph labels and keeps the true reward', () => {
    const activity = {matches: [{...match, map: '/Game/Maps/Duality/Duality', mode: 'Competitive', delta: '+21 RR'}], ranks: []} as unknown as ProfileActivity
    const html = renderToStaticMarkup(<LayerProvider><RankHistoryChart game="VALORANT" activity={activity} /></LayerProvider>)
    expect(html).toContain('Bind · +21 RR')
    expect(html).not.toContain('Duality')
    expect(html).not.toContain('/Game/Maps/')
  })
})
