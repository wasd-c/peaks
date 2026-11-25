import {renderToStaticMarkup} from 'react-dom/server'
import {describe, expect, it} from 'vitest'
import type {MatchPlayer} from '../types'
import {ValorantLiveScoreboard} from './ValorantLiveScoreboard'

const render = (players: MatchPlayer[]) => renderToStaticMarkup(
  <ValorantLiveScoreboard match={{game: 'VALORANT', phase: 'live', teams: [{name: 'Blue', players}]}} onSelectPlayer={() => undefined} />,
)
const text = (html: string) => html.replace(/<[^>]*>/g, '')
const displayedKda = (html: string) => [...html.matchAll(/<td class="vls-kda-cell">(.*?)<\/td>/g)].map(match => text(match[1]))

describe('live Valorant scoreboard statistics', () => {
  it('defaults to recent per-game averages when the game has shared only player history', () => {
    const html = render([{name: 'Jett#EU', overallStats: {matchesPlayed: 5, kills: 64, deaths: 50, assists: 25}}])
    expect(displayedKda(html)).toEqual(['12.8 / 10 / 5'])
    expect(html).toContain('Recent games')
  })

  it('keeps every player on the selected match scope even when one has only recent statistics', () => {
    const html = render([
      {name: 'Sage#1', stats: {kills: 0, deaths: 2}, overallStats: {matchesPlayed: 2, kills: 40}},
      {name: 'Omen#2', overallStats: {matchesPlayed: 2, kills: 36, deaths: 22, assists: 10}},
    ])
    expect(displayedKda(html)).toEqual(['0 / 2 / —', '— / — / —'])
  })

  it('preserves a legacy K/D/A summary without inferring combat statistics or exposing hidden identities', () => {
    const html = render([{name: 'PrivateId#EU', hidden: true, score: '8 / 0 / 2', statsLoading: true}])
    expect(displayedKda(html)).toEqual(['8 / 0 / 2'])
    expect(html).not.toContain('PrivateId')
    expect(html).not.toContain('Fetching player statistics')
    expect(html).toContain('Hidden player 1')
    expect(html).toMatch(/<td class="vls-metric" data-metric="ACS">—<\/td>/)
  })
})
