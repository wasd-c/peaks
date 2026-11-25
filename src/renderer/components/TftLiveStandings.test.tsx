import {renderToStaticMarkup} from 'react-dom/server'
import {describe, expect, it} from 'vitest'
import type {CurrentMatch, MatchPlayer} from '../types'
import {TftLiveStandings} from './TftLiveStandings'

const render = (players: MatchPlayer[], overrides?: Partial<CurrentMatch>) =>
  renderToStaticMarkup(<TftLiveStandings match={{game: 'Teamfight Tactics', phase: 'live', teams: [{name: 'Players', players}], ...overrides}} onSelectPlayer={() => undefined} />)
const table = (html: string) => html.slice(html.indexOf('<table'), html.indexOf('</table>'))
const scout = (html: string) => html.slice(html.indexOf('<aside'))

describe('TFT live standings', () => {
  it('orders the lobby by observed standing while opening scouting on the local player', () => {
    const html = render([
      {name: 'Local#TEST', self: true, stats: {health: 72.5, standing: 4, boardUnits: 0, observedAt: 1_800_000_000}, overallStats: {matchesPlayed: 4, placement: 10}},
      {name: 'Leader#TEST', stats: {health: 132, standing: 1, boardUnits: 7}},
    ])
    expect(table(html).indexOf('Scout Leader#TEST')).toBeLessThan(table(html).indexOf('Scout Local#TEST'))
    expect(table(html)).toContain('max="132"')
    expect(scout(html)).toContain('Local')
    expect(scout(html)).toContain('72.5')
    expect(scout(html)).toMatch(/Board units<\/dt><dd>0<\/dd>/)
    expect(scout(html)).toMatch(/Average placement<\/dt><dd>2.5<\/dd>/)
    expect(scout(html)).toContain('dateTime=')
    expect(scout(html)).not.toContain('Leader')
  })

  it('keeps a missing snapshot distinct from zero HP and suppresses unavailable rank blocks', () => {
    const html = render([
      {name: 'Self#TEST', self: true, stats: {placement: 2}, rank: 'Rank unavailable'},
      {name: 'Out#TEST', stats: {standing: 8, health: 0}},
    ])
    expect(table(html).match(/<meter\b/g)).toHaveLength(1)
    expect(table(html).match(/>Eliminated</g)).toHaveLength(1)
    expect(scout(html)).toContain('Statistics unavailable')
    expect(scout(html)).not.toContain('tft-scout-metrics')
    expect(scout(html)).not.toContain('Current rating')
    expect(scout(html)).not.toContain('Board units')
  })

  it('keeps verified Double Up pairs together and disables movement for stale or unassigned rosters', () => {
    const match: Partial<CurrentMatch> = {queue: '1160', teams: [
      {name: 'Duo 1', grouping: 'duo', players: [{name: 'Self#EU', self: true}, {name: 'Partner#EU'}]},
      {name: 'Players', grouping: 'unassigned', players: [{name: 'Solo#EU'}, {name: 'Other#EU'}]},
    ]}
    const html = render([], match)
    expect(table(html)).toContain('Your duo')
    expect(table(html)).toContain('Pairings unavailable')
    expect(table(html)).toContain('Reorder Partner#EU')
    expect(table(html)).not.toContain('Reorder Solo#EU')
    expect(table(render([], {...match, isStale: true}))).not.toContain('Reorder Partner#EU')
  })

  it('never exposes a hidden identity or scout data in text, assets, or accessible controls', () => {
    const html = render([{name: 'Secret#TEST', hidden: true, stats: {health: 97}, rank: 'Diamond III', composition: {units: [{id: 'SecretChampion', stars: 2}]}}])
    expect(html).toContain('Hidden player 1')
    expect(html).not.toContain('Secret')
    expect(html).not.toContain('Diamond')
    expect(html).not.toContain('Open profile for')
    expect(html).not.toContain('<meter')
  })
})
