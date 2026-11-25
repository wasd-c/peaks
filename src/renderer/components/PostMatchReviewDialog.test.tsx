import {renderToStaticMarkup} from 'react-dom/server'
import {expect, it} from 'vitest'
import {valorantAgentPortraitAsset, valorantRankAsset} from '../assets'
import type {Match} from '../types'
import {PostMatchReviewDialog} from './PostMatchReviewDialog'

const render = (match: Match) => renderToStaticMarkup(<PostMatchReviewDialog isOpen
  review={{key: 'match', account: {id: 'owner', riotId: 'Owner#EU', region: 'EUW', ranks: [{game: 'VALORANT', tier: 'diamond', division: '3'}]}, match}}
  onDismiss={() => {}} onOpenReport={() => {}} onShare={() => {}} />)

it('presents the owned side first and keeps a surrender verdict when the round count is misleading', () => {
  const html = render({game: 'VALORANT', mode: 'Competitive', result: 'Loss', delta: '-12 RR', teams: [
    {name: 'Red', score: 4, won: true, players: []},
    {name: 'Blue', score: 7, won: false, players: [{name: 'Owner#EU', self: true, agent: 'Jett', rankTier: 12}]},
  ]})
  expect(html).toContain('<b>7</b><i>:</i><b>4</b>')
  expect(html).toContain('>Defeat<')
  expect(html).toContain(valorantAgentPortraitAsset('Jett'))
  expect(html).toContain(valorantRankAsset('Gold 1'))
  expect(html).not.toContain('>Gold 1<')
  expect(html).not.toContain(valorantRankAsset('Diamond 3'))
})

it('uses the final TFT placement once and excludes a live standing and an unrecorded reward', () => {
  const html = render({game: 'Teamfight Tactics', mode: '1100', result: 'Top 4', teams: [
    {name: 'Lobby', players: [{name: 'Owner#EU', self: true, stats: {placement: 3, standing: 1, level: 8}}]},
  ]})
  expect(html).toContain('<i>#</i><b>3</b>')
  expect(html).not.toContain('<b>1</b>')
  expect(html).not.toContain('K/D/A')
  expect(html).not.toContain('match-recap__rating')
})

it('preserves an older account result when no roster arrived, without borrowing a rank or per-player statistics', () => {
  const html = render({game: 'VALORANT', result: 'Win', score: '13 — 8', mode: 'Competitive', delta: '+17 RR'})
  expect(html).toContain('<b>13</b><i>:</i><b>8</b>')
  expect(html).toContain('+17')
  expect(html).not.toContain('account-rank-emblem')
  expect(html).not.toContain('K/D/A')
})
