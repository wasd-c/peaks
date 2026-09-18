import {renderToStaticMarkup} from 'react-dom/server'
import {LayerProvider} from '@astryxdesign/core/Layer'
import {describe, expect, it} from 'vitest'
import {CurrentMatchScreen} from './CurrentMatchScreen'
import type {AppState, CurrentMatch, Game, SessionPhase} from '../types'

const render = (match: CurrentMatch, detected = true) => {
  const state: AppState = {
    locked: false, hasPasscode: true, pinMode: 'unlock', pinError: '', accounts: [], followed: [], searchHistory: [],
    currentMatch: match, gameDetected: detected,
    settings: {autoLockMinutes: 0, lockOnBlur: false, reduceMotion: false, riotApiConfigured: false, clipboardClearSeconds: 15},
    riotClient: {detected: true, label: 'Connected'},
  }
  return renderToStaticMarkup(<LayerProvider><CurrentMatchScreen state={state} onSelectPlayer={() => undefined} /></LayerProvider>)
}

const stages: [Game, SessionPhase, string][] = [
  ['VALORANT', 'lobby', 'Lobby'], ['League of Legends', 'matchmaking', 'In queue'],
  ['Teamfight Tactics', 'readycheck', 'Match found'], ['VALORANT', 'pregame', 'Agent select'],
  ['League of Legends', 'pregame', 'Champion select'], ['Teamfight Tactics', 'pregame', 'Getting ready'],
  ['Teamfight Tactics', 'live', 'In game'],
]

describe('Current match session stages', () => {
  it.each([true, false])('never uses a game artwork banner, detected=%s', detected => {
    const html = render({game: 'VALORANT', map: 'Ascent', teams: []}, detected)
    expect(html).not.toContain('background-image')
    expect(html).toContain('pd-riot-surface')
  })
  it.each(stages)('labels %s %s accurately', (game, phase, label) => {
    const html = render({game, phase, teams: []})
    expect(html).toContain(label.toUpperCase())
    expect(html).not.toContain('Unknown map')
    if (game === 'Teamfight Tactics') expect(html).not.toContain('Deathmatch')
    if (phase !== 'live') expect(html).not.toContain('This match')
  })

  it('uses the actual party count and queue mode without inventing a map, timer, or five-player team', () => {
    const html = render({
      game: 'Teamfight Tactics', phase: 'lobby', mode: 'Normal', queue: '1090', partySize: 3, partyMax: 8,
      teams: [{name: 'Party', players: [{name: 'You#EUW', self: true}, {name: 'One#EUW'}, {name: 'Two#EUW'}]}],
    })
    expect(html).toContain('3 / 8 players in your party')
    expect(html).toContain('Your lobby')
    expect(html).toContain('Normal')
    expect(html).not.toContain('1090')
    expect(html).not.toContain('Just started')
    expect(html).not.toContain('Agent unavailable')
    expect(html).not.toContain('Opponents')
    expect(html.match(/class="[^"]*pmc-card pmc-card--/g)).toHaveLength(3)
  })

  it('does not mistake party readiness for acceptance of a found match', () => {
    const html = render({game: 'League of Legends', phase: 'readycheck', elapsed: '00:42', teams: [{
      name: 'Party', score: 12, players: [{name: 'You#EUW', self: true, ready: true}, {name: 'Friend#EUW', ready: false}],
    }]})
    expect(html).toContain('00:42')
    expect(html).not.toContain('Accepted')
    expect(html).not.toContain('Pending')
    expect(html).toContain('Accept the match in your game client.')
    expect(html).not.toContain('pmc-team__score')
  })

  it('keeps the map, team score, and reordering without the tag legend in an active game', () => {
    const html = render({game: 'VALORANT', phase: 'live', mode: 'competitive', map: 'Ascent', elapsed: '18:20', teams: [
      {name: 'Blue', score: 9, players: [{name: 'You#EUW', self: true}, {name: 'Friend#EUW'}]},
      {name: 'Red', score: 5, players: [{name: 'Opponent#EUW'}]},
    ]})
    expect(html).toContain('Ascent')
    expect(html).toContain('Competitive')
    expect(html.replace(/<[^>]+>/g, '')).toContain('9 : 5')
    expect(html).not.toContain('pmc-legend')
    expect(html).not.toContain('This match')
    expect(html).not.toContain('Past games')
    expect(html).toContain('Reorder You#EUW')
  })

  it.each(['VALORANT', 'League of Legends'] as const)('keeps the friendly score green when %s supplies opponents first', game => {
    const html = render({game, phase: 'live', teams: [
      {name: 'Red', score: 1, players: [{name: 'Opponent#EUW'}]},
      {name: 'Blue', score: 4, players: [{name: 'You#EUW', self: true}]},
    ]})
    expect(html.replace(/<[^>]+>/g, '')).toContain('4 : 1')
    expect(html).toMatch(/class="[^"]*pmc-score--ally[^"]*"[^>]*>4</)
    expect(html).toMatch(/class="[^"]*pmc-score--enemy[^"]*"[^>]*>1</)
  })

  it('keeps scores neutral if the local player is not identified', () => {
    const html = render({game: 'VALORANT', phase: 'live', teams: [
      {name: 'Blue', score: 4, players: [{name: 'Player#EUW'}]},
      {name: 'Red', score: 1, players: [{name: 'Opponent#EUW'}]},
    ]})
    expect(html).not.toContain('pmc-score--ally')
    expect(html).not.toContain('pmc-score--enemy')
  })

  it('does not enable card movement while a roster is stale', () => {
    const html = render({game: 'League of Legends', phase: 'pregame', isStale: true, teams: [{name: 'Blue', players: [{name: 'You#EUW'}, {name: 'Other#EUW'}]}]})
    expect(html).toContain('AWAITING UPDATE')
    expect(html).not.toContain('Reorder You#EUW')
  })

  it('names all supported games in the empty session state', () => {
    const html = render({}, false)
    for (const game of ['VALORANT', 'League of Legends', 'Teamfight Tactics']) expect(html).toContain(game)
    expect(html).toContain('No active session')
  })
})
