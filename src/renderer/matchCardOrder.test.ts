import {describe, expect, it} from 'vitest'
import valorantIndex from '../peaks/ui/assets/riot/valorant/index.json'
import {alignValorantMatchup, moveTeamCard, valorantCardRole} from './matchCardOrder'
import type {MatchPlayer} from './types'

const roster = (...agents: (string | undefined)[]): MatchPlayer[] => agents.map((agent, index) => ({name: `Player ${index}`, agent}))
const names = (players: MatchPlayer[]) => players.map(player => player.agent)
const exactMatches = (teams: [MatchPlayer[], MatchPlayer[]]) => teams[0].filter((player, index) => {
  const role = valorantCardRole(player.agent)
  return role !== undefined && role === valorantCardRole(teams[1][index]?.agent)
}).length

describe('role-aligned player columns', () => {
  it('recognizes every bundled agent by name and UUID with an explicit subgroup', () => {
    for (const agent of valorantIndex.agents) {
      const role = valorantCardRole(agent.displayName)
      expect(role, agent.displayName).toBeDefined()
      expect(valorantCardRole(agent.uuid.toUpperCase())).toBe(role)
      expect(valorantCardRole(` ${agent.displayName.toUpperCase()} `)).toBe(role)
    }
    expect(valorantCardRole('kayo')).toBe('initiator')
    expect(valorantCardRole('Miks')).toBe('controller')
    expect(valorantCardRole('Veto')).toBe('sentinel')
    expect(valorantCardRole('Yoru')).toBe('space-duelist')
    expect(valorantCardRole('Iso')).toBe('ego-duelist')
    expect(valorantCardRole('Unknown future agent')).toBeUndefined()
    expect(valorantCardRole()).toBeUndefined()
  })

  it('aligns each role, splitting entry and ego duelists into distinct columns', () => {
    const result = alignValorantMatchup(roster('Cypher', 'Omen', 'Reyna', 'Sova', 'Jett'), roster('Fade', 'Raze', 'Killjoy', 'Phoenix', 'Brimstone'))
    expect(names(result[0])).toEqual(['Jett', 'Reyna', 'Sova', 'Omen', 'Cypher'])
    expect(names(result[1])).toEqual(['Raze', 'Phoenix', 'Fade', 'Brimstone', 'Killjoy'])
    expect(exactMatches(result)).toBe(5)
  })

  it('never spends an available exact role match on an earlier duelist fallback', () => {
    const result = alignValorantMatchup(roster('Jett', 'Reyna', 'Sova', 'Omen', 'Cypher'), roster('Reyna', 'Omen', 'Cypher', 'Sova', 'Chamber'))
    expect(exactMatches(result)).toBe(4)
    expect(names(result[1])).toEqual(['Chamber', 'Reyna', 'Sova', 'Omen', 'Cypher'])
  })

  it('mirrors agents inside a role and pairs leftover duelists before unrelated roles', () => {
    expect(names(alignValorantMatchup(roster('Jett', 'Raze'), roster('Raze', 'Jett'))[1])).toEqual(['Jett', 'Raze'])
    expect(names(alignValorantMatchup(roster('Jett', 'Sova'), roster('Omen', 'Reyna'))[1])).toEqual(['Reyna', 'Omen'])
  })

  it('attains the mathematical maximum of exact matches across mixed and uneven compositions', () => {
    const choices = ['Jett', 'Reyna', 'Sova', 'Omen', 'Cypher', undefined]
    let seed = 4_291
    const next = () => { seed = (seed * 1664525 + 1013904223) >>> 0; return choices[seed % choices.length] }
    for (let sample = 0; sample < 200; sample++) {
      const first = roster(...Array.from({length: 5}, next))
      const second = roster(...Array.from({length: 5}, next))
      const maximum = choices.filter(Boolean).reduce((sum, agent) => sum + Math.min(
        first.filter(player => valorantCardRole(player.agent) === valorantCardRole(agent)).length,
        second.filter(player => valorantCardRole(player.agent) === valorantCardRole(agent)).length,
      ), 0)
      expect(exactMatches(alignValorantMatchup(first, second))).toBe(maximum)
    }
  })

  it('preserves players, duplicate identities, self flags and frozen inputs without mutation', () => {
    const first = Object.freeze(roster('Omen', 'Jett', 'Jett').map((player, index) => Object.freeze({...player, name: 'Hidden player', hidden: true, self: index === 1})))
    const second = Object.freeze(roster('Raze', 'Brimstone', 'Neon').map(player => Object.freeze(player)))
    const before = JSON.stringify([first, second])
    const result = alignValorantMatchup(first, second)
    expect(JSON.stringify([first, second])).toBe(before)
    for (const player of first) expect(result[0]).toContain(player)
    for (const player of second) expect(result[1]).toContain(player)
    expect(result[0].filter(player => player.self)).toHaveLength(1)
    expect(alignValorantMatchup(first, second)).toEqual(result)
  })

  it('keeps unknown ties stable and handles empty, short and oversized rosters', () => {
    const unknowns = roster(undefined, 'Unreleased')
    expect(alignValorantMatchup(unknowns, unknowns)).toEqual([unknowns, unknowns])
    expect(alignValorantMatchup([], unknowns)).toEqual([[], unknowns])
    const result = alignValorantMatchup(roster('Omen', 'Sova', 'Jett'), roster('Jett'))
    expect(names(result[0])[0]).toBe('Jett')
    expect(result[0]).toHaveLength(3)
    expect(result[1]).toHaveLength(1)
    const oversized = roster('Omen', 'Sova', 'Jett', 'Reyna', 'Cypher', 'Sage')
    expect(alignValorantMatchup(oversized, unknowns)).toEqual([oversized, unknowns])
  })
})

describe('manual team card order', () => {
  it('moves a card within its own team while leaving other teams untouched', () => {
    const groups = Object.freeze([Object.freeze(['a', 'b', 'c']), Object.freeze(['d', 'e', 'f'])])
    expect(moveTeamCard(groups, {team: 0, index: 0}, {team: 0, index: 2})).toEqual([['b', 'c', 'a'], ['d', 'e', 'f']])
    expect(groups).toEqual([['a', 'b', 'c'], ['d', 'e', 'f']])
  })

  it.each([
    [{team: 0, index: 0}, {team: 1, index: 1}],
    [{team: 4, index: 0}, {team: 4, index: 1}],
    [{team: 0, index: -1}, {team: 0, index: 1}],
    [{team: 0, index: 0}, {team: 0, index: 5}],
    [{team: 0, index: 0.5}, {team: 0, index: 1}],
  ])('rejects cross-team or invalid moves %j -> %j', (from, to) => {
    expect(moveTeamCard([['a', 'b'], ['c']], from, to)).toEqual([['a', 'b'], ['c']])
  })
})
