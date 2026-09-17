import {describe, expect, it} from 'vitest'

import type {Match} from './types'
import {valorantInsights} from './valorantInsights'

const matches: Match[] = [
  {
    id: 'one',
    game: 'VALORANT',
    result: 'Victory',
    mode: 'Competitive',
    map: 'Abyss',
    delta: '+21 RR',
    teams: [{
      name: 'Your team',
      players: [
        {
          name: 'Peak#EU',
          riotId: 'Peak#EU',
          self: true,
          agent: 'Omen',
          stats: {
            kills: 20,
            deaths: 10,
            assists: 5,
            combatScore: 5_200,
            roundsPlayed: 20,
            damage: 3_000,
            headshots: 10,
            bodyshots: 20,
            legshots: 0,
          },
        },
        {name: 'Duo#EU', riotId: 'Duo#EU', agent: 'Sova'},
      ],
    }],
  },
  {
    id: 'two',
    game: 'VALORANT',
    result: 'Defeat',
    mode: 'Competitive',
    map: 'Abyss',
    delta: '-14 RR',
    teams: [{
      name: 'Your team',
      players: [
        {
          name: 'Peak#EU',
          riotId: 'Peak#EU',
          self: true,
          agent: 'Jett',
          stats: {
            kills: 10,
            deaths: 20,
            assists: 2,
            combatScore: 4000,
            roundsPlayed: 20,
            headshots: 5,
            bodyshots: 5,
            legshots: 0,
          },
        },
        {name: 'Duo#EU', riotId: 'Duo#EU', agent: 'Sova'},
      ],
    }],
  },
  {id: 'league', game: 'League of Legends', result: 'Win'},
]

describe('valorantInsights', () => {
  it('calculates combat, rank, agent, map, and teammate insights from sanitized matches', () => {
    const insights = valorantInsights(matches, 'Peak#EU')

    expect(insights.matches).toBe(2)
    expect(insights.winRate).toBe(50)
    expect(insights.kd).toBe(1)
    expect(insights.averageCombatScore).toBe(230)
    expect(insights.averageDamagePerRound).toBe(150)
    expect(insights.headshotRate).toBe(37.5)
    expect(insights.rrDelta).toBe(7)
    expect(insights.maps[0]).toMatchObject({label: 'Abyss', games: 2, wins: 1, losses: 1})
    expect(insights.agents.map(agent => agent.label)).toEqual(['Omen', 'Jett'])
    expect(insights.teammates[0]).toMatchObject({riotId: 'Duo#EU', games: 2, wins: 1, winRate: 50})
    expect(insights.trend[0]).toMatchObject({id: 'one', kda: '20 / 10 / 5', rrDelta: 21})
  })

  it('does not invent rates when no Valorant match data is available', () => {
    const insights = valorantInsights([{game: 'Teamfight Tactics', result: 'Placement'}], 'Peak#EU')

    expect(insights.matches).toBe(0)
    expect(insights.winRate).toBeUndefined()
    expect(insights.kd).toBeUndefined()
    expect(insights.rrDelta).toBeUndefined()
    expect(insights.agents).toEqual([])
    expect(insights.trend).toEqual([])
  })

  it('does not present total combat score as ACS or estimate missing hit locations', () => {
    const insights = valorantInsights([{
      game: 'VALORANT', result: 'Win',
      teams: [{name: 'Team', players: [{name: 'Peak#EU', self: true, stats: {combatScore: 5200, headshots: 20}}]}],
    }], 'Peak#EU')
    expect(insights.averageCombatScore).toBeUndefined()
    expect(insights.headshotRate).toBeUndefined()
  })

  it('uses the requested visible player rather than a different self-marked player', () => {
    const insights = valorantInsights([{
      game: 'VALORANT', result: 'Win',
      teams: [{name: 'Team', players: [
        {name: 'Owner#EU', self: true, stats: {kills: 30, deaths: 5}},
        {name: 'Profile#EU', stats: {kills: 8, deaths: 10}},
      ]}],
    }], 'Profile#EU')
    expect(insights.kd).toBe(0.8)
  })

  it('keeps missing RR blank and never counts Deathmatch opponents as teammates', () => {
    const insights = valorantInsights([{
      id: 'deathmatch',
      game: 'VALORANT',
      result: 'Placement',
      mode: 'Deathmatch',
      freeForAll: true,
      teams: [{
        name: 'Free for all',
        players: [
          {name: 'Peak#EU', riotId: 'Peak#EU', self: true},
          {name: 'Opponent#EU', riotId: 'Opponent#EU'},
        ],
      }],
    }], 'Peak#EU')

    expect(insights.rrDelta).toBeUndefined()
    expect(insights.teammates).toEqual([])
  })
})
