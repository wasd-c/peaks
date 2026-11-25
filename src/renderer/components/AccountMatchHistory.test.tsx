import {renderToStaticMarkup} from 'react-dom/server'
import {expect, it} from 'vitest'
import type {Account, Match} from '../types'
import {AccountMatchHistory} from './AccountMatchHistory'
import {knownValorantMapAsset, valorantRankAsset} from '../assets'

it('orders dated games across titles and keeps undated records in their original order', () => {
  const base: Match = {game: 'VALORANT', result: 'Unknown'}
  const matches: Match[] = [
    {...base, map: 'First undated'}, {...base, map: 'Ascent', playedAtTimestamp: 10},
    {...base, map: 'Second undated'}, {...base, game: 'Teamfight Tactics', map: 'Latest arena', playedAtTimestamp: 20},
  ]
  const account: Account = {id: 'demo', riotId: 'Owner#TEST', region: 'EUW', ranks: [], peakRanks: [], matches}
  const html = renderToStaticMarkup(<AccountMatchHistory account={account} onSelect={() => undefined} />)
  const matchButtons = Array.from(html.matchAll(/<strong>([^<]+)<\/strong>/g), hit => hit[1])
  expect(matchButtons).toEqual(['Latest arena', 'Ascent', 'First undated', 'Second undated'])
  expect(matches[0].map).toBe('First undated')
})

it('shows the recorded division and round score, including a surrender against the run of play', () => {
  const match: Match = {game: 'VALORANT', mode: 'Competitive', map: 'Sunset', result: 'Defeat', delta: '-11 RR', teams: [
    {name: 'Blue', score: 9, won: false, players: [{name: 'Owner#TEST', self: true, rankTier: 12, currentRank: 'Diamond 3'}]},
    {name: 'Red', score: 5, won: true, players: []},
  ]}
  const account: Account = {id: 'demo', riotId: 'Owner#TEST', region: 'EUW', ranks: [], peakRanks: [], matches: [match]}
  const html = renderToStaticMarkup(<AccountMatchHistory account={account} onSelect={() => undefined} />)
  expect(html).toContain(knownValorantMapAsset('Sunset'))
  expect(html).toContain(valorantRankAsset('Gold 1'))
  expect(html).not.toContain('>Gold 1<')
  expect(html).not.toContain('Diamond 3')
  expect(html).not.toContain('<table')
  expect(html).toMatch(/<b>9<\/b><i>:<\/i><b>5<\/b>/)
  expect(html).toContain('<small>Defeat</small>')
})
