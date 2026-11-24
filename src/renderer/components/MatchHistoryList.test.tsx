import {LayerProvider} from '../ui'
import {renderToStaticMarkup} from 'react-dom/server'
import {describe, expect, it} from 'vitest'
import {findAccountIcon} from '../accountIcons'
import type {Match, MatchPlayer} from '../types'
import {MatchHistoryList} from './MatchHistoryList'

const owner: MatchPlayer = {name: 'Owner#TEST', self: true, agent: 'Jett', rank: 'Ascendant 2', currentRank: 'Immortal 3', stats: {kills: 18, deaths: 12, assists: 3}}
const visitor: MatchPlayer = {name: 'Visitor#TEST', agent: 'Omen', rank: 'Diamond 3', stats: {kills: 16, deaths: 15, assists: 4}}
const extras = {map: 'Hidden map label', playedAt: 'Wednesday, 16 September 2026', duration: '37:42', durationSeconds: 2262, performance: 'Hidden performance label'}
const valorant = (mode = 'Competitive'): Match => ({id: 'val-match', game: 'VALORANT', mode, result: 'Win', agent: 'Jett', delta: '+21 RR', ...extras,
  teams: [{name: 'Red', won: true, score: 13, players: [owner]}, {name: 'Blue', won: false, score: 8, players: [visitor]}]})
const league = (mode = '400'): Match => ({id: 'lol-match', game: 'League of Legends', mode, result: 'Win', agent: '103', delta: '+24 LP', ...extras,
  teams: [{name: 'Blue', won: true, players: [{...owner, agent: '103', rank: 'Gold IV', stats: {kills: 8, deaths: 2, assists: 11}}]}]})
const tft = (): Match => ({id: 'tft-match', game: 'Teamfight Tactics', mode: '1090', result: 'Win', agent: 'TFT tactician', delta: '+30 LP', score: '#4', ...extras,
  teams: [{name: 'Lobby', players: [{...owner, agent: 'TFT tactician', rank: 'Emerald II', stats: {placement: 4}}, {...visitor, agent: 'TFT_Pengu', rank: 'Diamond II', stats: {placement: 7}}]}]})

function render(matches: Match[], riotId = owner.name) {
  return renderToStaticMarkup(<LayerProvider><MatchHistoryList matches={matches} riotId={riotId} heading={null} onSelect={() => undefined} /></LayerProvider>)
}

// Attribute text (including portrait hover labels) is not inline row text.
const visibleText = (html: string) => html.replace(/<style\b[^>]*>[\s\S]*?<\/style>/gi, '').replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim()
const portrait = (game: 'VALORANT' | 'League of Legends', characterId: string) => findAccountIcon({game, characterId})!.image

describe('compact match history presentation', () => {
  it('renders a TFT result as placement only, without a tactician portrait or queue metadata', () => {
    const html = render([tft()])
    expect(visibleText(html)).toBe('#4')
    expect(html).toContain('alt="Teamfight Tactics"')
    expect(html).toContain('data-placement="4"')
    expect(html).not.toContain('pd-match-history__character')
    for (const value of ['TFT tactician', 'TFT_Pengu', '1090', extras.map, extras.playedAt, extras.duration, extras.performance]) {
      expect(html).not.toContain(value)
    }
  })

  it('shows League and VALORANT portraits, results and their own score formats without inline character names', () => {
    const html = render([league(), valorant('unrated')])
    const text = visibleText(html)
    expect(text).toContain('Victory')
    expect(text).toContain('8/2/11')
    expect(text).toContain('13-8')
    expect(html).toContain(portrait('League of Legends', 'Ahri'))
    expect(html).toContain(portrait('VALORANT', 'Jett'))
    expect((html.match(/pd-match-history__character/g) ?? [])).toHaveLength(2)
    for (const value of ['Ahri', 'Jett', '103', '400', 'unrated', extras.map, extras.playedAt, extras.duration, extras.performance]) {
      expect(text).not.toContain(value)
    }
  })

  it.each([['VALORANT', () => valorant('unrated')], ['League of Legends', () => league('400')], ['Teamfight Tactics', tft]] as const)(
    'does not leak historical/current rank or rewards into normal %s rows', (_game, fixture) => {
      const html = render([fixture()])
      expect(html).not.toContain('pd-match-history__rating')
      expect(html).not.toContain('pd-match-history__rank')
      expect(html).not.toContain('pd-match-history__delta')
      for (const value of ['Ascendant 2', 'Gold IV', 'Emerald II', 'Immortal 3', '+21', '+24', '+30']) expect(visibleText(html)).not.toContain(value)
    },
  )

  it('retains known historical rank and the explicit reward for the ranked owner', () => {
    const html = render([valorant()])
    const text = visibleText(html)
    expect(text).toContain('Victory')
    expect(text).toContain('13-8')
    expect(text).toContain('Ascendant 2')
    expect(text).toContain('+21')
    expect(html).toContain('aria-label="+21 RR"')
    expect(text).not.toContain('Immortal 3')
    expect(text).not.toContain('Competitive')
    expect(text).not.toContain('Jett')
  })

  it('renders the clicked player’s portrait, score and rank instead of another player marked self', () => {
    const html = render([valorant()], visitor.name)
    const text = visibleText(html)
    expect(text).toContain('Defeat')
    expect(text).toContain('8-13')
    expect(text).toContain('Diamond 3')
    expect(html).toContain(portrait('VALORANT', 'Omen'))
    expect(html).not.toContain(portrait('VALORANT', 'Jett'))
    expect(html).not.toContain('pd-match-history__delta')
    for (const value of ['Victory', '13-8', 'Ascendant 2', '+21', owner.name, visitor.name, 'Omen']) expect(text).not.toContain(value)
  })

  it('uses the clicked TFT player’s placement and never reuses the owner summary', () => {
    const html = render([tft()], visitor.name)
    expect(visibleText(html)).toBe('#7')
    expect(html).toContain('data-placement="7"')
    expect(html).not.toContain('pd-match-history__character')
    expect(html).not.toContain('pd-match-history__rating')
  })

  it('keeps an unknown target empty rather than showing another person’s result or character', () => {
    const html = render([valorant()], 'Absent#TEST')
    expect(visibleText(html)).toBe('—')
    expect(html).not.toContain('pd-match-history__character')
    expect(html).not.toContain('pd-match-history__rating')
    expect(html).not.toContain('Victory')
    expect(html).not.toContain('13-8')
  })
})
