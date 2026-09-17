import {describe, expect, it} from 'vitest'
import {createElement} from 'react'
import {renderToStaticMarkup} from 'react-dom/server'

import {MatchList, rankRatingLabel} from './shared'
import type {Match} from '../types'

describe('game-specific rank rating labels', () => {
  it('uses RR for VALORANT and LP for League/TFT', () => {
    expect(rankRatingLabel('VALORANT', 72)).toBe('72 RR')
    expect(rankRatingLabel('League of Legends', 72)).toBe('72 LP')
    expect(rankRatingLabel('Teamfight Tactics', 72)).toBe('72 LP')
  })
})

describe('match history presentation', () => {
  const renderMatch = (match: Match) => renderToStaticMarkup(createElement(MatchList, {
    matches: [match],
    onSelect: () => undefined,
  }))

  it('leads the match action with its map and shows the player agent from team evidence', () => {
    const markup = renderMatch({game: 'VALORANT', result: 'Win', map: 'Infinity', mode: 'Competitive', teams: [{name: 'Allies', players: [{name: 'Player', self: true, agent: '8e253930-4c05-31dd-1b6c-968525494517'}]}]})
    expect(markup).toMatch(/<button[^>]*><span[^>]*>Abyss<\/span>/)
    expect(markup).toContain('Omen')
    expect(markup).toContain('Competitive')
  })

  it('shows explicit agent metadata for summary history without a full roster', () => {
    const markup = renderMatch({game: 'VALORANT', result: 'Win', map: 'Ascent', agent: 'Jett'})
    expect(markup).toMatch(/<button[^>]*><span[^>]*>Ascent<\/span>/)
    expect(markup).toContain('Jett')
  })

  it('preserves League and TFT history without requiring an agent', () => {
    expect(renderMatch({game: 'League of Legends', result: 'Win', map: 'Summoners Rift'})).toMatch(/<button[^>]*><span[^>]*>Summoners Rift<\/span>/)
    expect(renderMatch({game: 'Teamfight Tactics', result: 'Top 4'})).toMatch(/<button[^>]*><span[^>]*>Teamfight Tactics<\/span>/)
  })
})
