import {renderToStaticMarkup} from 'react-dom/server'
import {expect, it} from 'vitest'
import type {Account, Match} from '../types'
import {AccountMatchHistory} from './AccountMatchHistory'

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
