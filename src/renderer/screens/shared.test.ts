import {describe, expect, it} from 'vitest'
import {createElement} from 'react'
import {renderToStaticMarkup} from 'react-dom/server'
import {LayerProvider} from '../ui'

import {MatchList, rankRatingLabel} from './shared'
import {findAccountIcon} from '../accountIcons'
import type {Match} from '../types'

describe('game-specific rank rating labels', () => {
  it('uses RR for VALORANT and LP for League/TFT', () => {
    expect(rankRatingLabel('VALORANT', 72)).toBe('72 RR')
    expect(rankRatingLabel('League of Legends', 72)).toBe('72 LP')
    expect(rankRatingLabel('Teamfight Tactics', 72)).toBe('72 LP')
  })
})

describe('match history presentation', () => {
  const renderMatch = (match: Match) => renderToStaticMarkup(createElement(LayerProvider, null, createElement(MatchList, {
    matches: [match],
    onSelect: () => undefined,
  })))
  const actionText = (markup: string) => markup.match(/<button\b[^>]*>[\s\S]*?<\/button>/)?.[0].replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim()

  it('keeps an accessible match action with the result, score and portrait from team evidence', () => {
    const markup = renderMatch({game: 'VALORANT', result: 'Win', score: '13 — 5', map: 'Infinity', mode: 'Competitive', teams: [{name: 'Allies', players: [{name: 'Player', self: true, agent: '8e253930-4c05-31dd-1b6c-968525494517'}]}]})
    expect(actionText(markup)).toBe('Victory 13-5')
    expect(markup).toContain(findAccountIcon({game: 'VALORANT', characterId: 'Omen'})!.image)
    expect(markup).toContain('pd-match-history__character')
    expect(actionText(markup)).not.toContain('Omen')
    for (const value of ['Abyss', 'Infinity', 'Competitive']) expect(markup).not.toContain(value)
  })

  it('shows explicit agent metadata for summary history without a full roster', () => {
    const markup = renderMatch({game: 'VALORANT', result: 'Win', map: 'Ascent', agent: 'Jett', score: '13:5'})
    expect(actionText(markup)).toBe('Victory 13-5')
    expect(markup).toContain(findAccountIcon({game: 'VALORANT', characterId: 'Jett'})!.image)
    expect(actionText(markup)).not.toContain('Jett')
    expect(markup).not.toContain('Ascent')
  })

  it('preserves League and TFT history without requiring an agent', () => {
    const league = renderMatch({game: 'League of Legends', result: 'Win', map: 'Summoners Rift'})
    const tft = renderMatch({game: 'Teamfight Tactics', result: 'Top 4'})
    expect(league).toContain('alt="League of Legends"')
    expect(actionText(league)).toBe('Victory')
    expect(league).not.toContain('Summoners Rift')
    expect(tft).toContain('alt="Teamfight Tactics"')
    expect(actionText(tft)).toBe('—')
    expect(tft).not.toContain('#4')
    expect(league).not.toContain('pd-match-history__character')
    expect(tft).not.toContain('pd-match-history__character')
  })
})
