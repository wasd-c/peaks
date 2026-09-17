import {describe, expect, it} from 'vitest'
import {matchGridColumns, resolveMatchLayout} from './matchLayout'
import type {MatchTeam} from './types'

const roster = (count: number, name = 'Team'): MatchTeam => ({
  name,
  players: Array.from({length: count}, (_, index) => ({name: `${name} ${index + 1}`})),
})

describe('adaptive match layouts', () => {
  it.each(['lobby', 'matchmaking', 'readycheck'] as const)('preserves parties before an FFA game during %s', phase => {
    const teams = [roster(3, 'Party')]
    const layout = resolveMatchLayout({game: 'VALORANT', mode: 'Deathmatch', freeForAll: true, phase, teams})
    expect(layout.kind).toBe('roster')
    expect(layout.groups).toEqual(teams)
  })

  it('uses an eight-player TFT field without invented teams or a deathmatch label', () => {
    const layout = resolveMatchLayout({game: 'Teamfight Tactics', phase: 'live', freeForAll: true, teams: [roster(8)]})
    expect(layout.groups).toHaveLength(1)
    expect(layout.groups[0].name).toBe('Players')
    expect(layout.groups[0].players).toHaveLength(8)
    expect(layout.canAlignRoles).toBe(false)
  })

  it.each(['1150', '1160'])('preserves verified Double Up pairs for queue %s despite a legacy FFA flag', queueId => {
    const teams = Array.from({length: 4}, (_, index) => ({...roster(2, `Duo ${index + 1}`), grouping: 'duo' as const}))
    const layout = resolveMatchLayout({game: 'Teamfight Tactics', queueId, freeForAll: true, teams})
    expect(layout.kind).toBe('duos')
    expect(layout.groups).toEqual(teams)
    expect(layout.groups).not.toBe(teams)
    expect(layout.canAlignRoles).toBe(false)
  })

  it.each(['Double Up', 'Double Up (Workshop)', 'TFT_PAIRS', '1150', '1160', 'RANKED_TFT_DOUBLE_UP', 'RANKED_TFT_PAIRS', 'pairs', 'TFT_DOUBLE_UP'])('recognizes report mode %s while retaining only actual pairs', mode => {
    const pair = {...roster(2, 'Duo 1'), grouping: 'duo' as const}
    const unknown = roster(6, 'Players')
    const layout = resolveMatchLayout({game: 'Teamfight Tactics', mode, freeForAll: true, teams: [pair, unknown]})
    expect(layout.kind).toBe('duos')
    expect(layout.groups[0]).toBe(pair)
    expect(layout.groups[1]).toEqual({...unknown, grouping: 'unassigned'})
  })

  it.each(['RANKED_TFT_DOUBLE_UP', 'RANKED_TFT_PAIRS'])('recognizes authenticated queue label %s', queueId => {
    expect(resolveMatchLayout({game: 'Teamfight Tactics', queueId, teams: [roster(8)]}).kind).toBe('duos')
  })

  it.each(['1090', '1100', '1130'])('prioritizes non-duo queue %s over a stale Double Up label', queueId => {
    const input = {game: 'Teamfight Tactics' as const, queueId, mode: 'Double Up', freeForAll: true, teams: [roster(8)]}
    expect(resolveMatchLayout(input).kind).toBe('free-for-all')
    expect(resolveMatchLayout({...input, teamMode: 'duos'}).kind).toBe('duos')
  })

  it('never guesses Double Up pairs from eight lobby members or an incomplete roster', () => {
    const players = roster(8, 'Party').players
    const layout = resolveMatchLayout({game: 'Teamfight Tactics', teamMode: 'duos', phase: 'lobby', teams: [{name: 'Party', players}]})
    expect(layout.groups).toEqual([{name: 'Players', grouping: 'unassigned', players}])
    expect(resolveMatchLayout({game: 'Teamfight Tactics', teamMode: 'duos', teams: [roster(2, 'Party')]}).groups[0].grouping).toBe('unassigned')
    expect(resolveMatchLayout({game: 'Teamfight Tactics', teamMode: 'duos', teams: []}).groups).toEqual([])
  })

  it('retains a confirmed partial duo and rejects a malformed oversized pair or explicit unknown group', () => {
    const partial = {...roster(1, 'Duo 1'), grouping: 'duo' as const}
    const oversized = {...roster(3, 'Duo 2'), grouping: 'duo' as const}
    const unknown = {...roster(2, 'Duo 3'), grouping: 'unassigned' as const}
    const layout = resolveMatchLayout({game: 'Teamfight Tactics', mode: 'Double Up', teams: [partial, oversized, unknown]})
    expect(layout.groups[0]).toBe(partial)
    expect(layout.groups[1]).toEqual({name: 'Players', grouping: 'unassigned', players: [...oversized.players, ...unknown.players]})
  })

  it('does not turn a League duo queue or ordinary TFT party into Double Up', () => {
    expect(resolveMatchLayout({game: 'League of Legends', mode: 'Ranked Solo / Duo', teams: [roster(5), roster(5)]}).kind).toBe('teams')
    expect(resolveMatchLayout({game: 'Teamfight Tactics', queueId: '1090', freeForAll: true, teams: [roster(8)]}).kind).toBe('free-for-all')
  })

  it('merges Deathmatch source buckets into one scoreless free-for-all grid', () => {
    const own = {...roster(1, 'Self'), score: 13, won: true}
    own.players[0].self = true
    const others = {...roster(13, 'Others'), score: 8, won: false}
    const layout = resolveMatchLayout({game: 'VALORANT', mode: 'Deathmatch', teams: [own, others]})
    expect(layout.kind).toBe('free-for-all')
    expect(layout.canAlignRoles).toBe(false)
    expect(layout.groups).toHaveLength(1)
    expect(layout.groups[0].players).toEqual([...own.players, ...others.players])
    expect(layout.groups[0].players[0]).toBe(own.players[0])
    expect(layout.groups[0]).not.toHaveProperty('score')
    expect(layout.groups[0]).not.toHaveProperty('won')
  })

  it.each(['Team Deathmatch', 'TeamDeathmatch', 'Gauntlet: Glitched', 'Retake', 'Skirmish'])('does not guess free-for-all from %s', mode => {
    expect(resolveMatchLayout({game: 'VALORANT', mode, teams: [roster(3), roster(3)]}).kind).toBe('teams')
  })

  it('honors explicit classification and native queue evidence before display labels', () => {
    const teams = [roster(2), roster(2)]
    expect(resolveMatchLayout({game: 'VALORANT', mode: 'Deathmatch', freeForAll: false, teams}).kind).toBe('teams')
    expect(resolveMatchLayout({game: 'VALORANT', mode: 'Unknown', freeForAll: true, teams}).kind).toBe('free-for-all')
    expect(resolveMatchLayout({game: 'VALORANT', queueId: 'hurm', mode: 'Deathmatch', teams}).kind).toBe('teams')
    expect(resolveMatchLayout({game: 'VALORANT', queueId: 'deathmatch', mode: 'Unknown', teams}).kind).toBe('free-for-all')
  })

  it('recognizes an exact native Deathmatch asset without matching unrelated modes', () => {
    const teams = [roster(8)]
    expect(resolveMatchLayout({game: 'VALORANT', gameMode: '/Game/GameModes/Deathmatch/DeathmatchGameMode.DeathmatchGameMode_C', teams}).kind).toBe('free-for-all')
    expect(resolveMatchLayout({game: 'VALORANT', modeId: '/Game/GameModes/Deathmatch/Deathmatch_GameMode.Deathmatch_GameMode', mode: 'Live match', teams}).kind).toBe('free-for-all')
    expect(resolveMatchLayout({game: 'VALORANT', mode: '/Game/GameModes/Deathmatch/Deathmatch_GameMode.Deathmatch_GameMode', teams}).kind).toBe('free-for-all')
    expect(resolveMatchLayout({game: 'VALORANT', gameMode: '/Game/GameModes/HURM/HURMGameMode.HURMGameMode_C', teams}).kind).toBe('roster')
    expect(resolveMatchLayout({game: 'VALORANT', modeId: '/Game/GameModes/HURM/HURMGameMode.HURMGameMode_C', mode: 'Deathmatch', teams}).kind).toBe('roster')
    expect(resolveMatchLayout({game: 'League of Legends', mode: 'Deathmatch', teams}).kind).toBe('roster')
  })

  it('preserves eight distinct duo teams for Gauntlet and future multiteam modes', () => {
    const teams = Array.from({length: 8}, (_, index) => roster(2, `Team ${index + 1}`))
    for (const mode of ['Gauntlet: Glitched', 'Future mode']) {
      const layout = resolveMatchLayout({game: 'VALORANT', mode, teams})
      expect(layout.kind).toBe('teams')
      expect(layout.groups).toEqual(teams)
      expect(layout.groups).not.toBe(teams)
      expect(layout.canAlignRoles).toBe(false)
      expect(layout.groups.map(group => matchGridColumns(group.players.length).max)).toEqual(Array(8).fill(2))
    }
  })

  it('sizes Retake and asymmetric Skirmish using actual rosters rather than mode defaults', () => {
    const retake = resolveMatchLayout({game: 'VALORANT', mode: 'Retake', teams: [roster(3), roster(3)]})
    expect(retake.canAlignRoles).toBe(true)
    expect(retake.groups.map(team => matchGridColumns(team.players.length).max)).toEqual([3, 3])
    const skirmish = resolveMatchLayout({game: 'VALORANT', mode: 'Skirmish', teams: [roster(2), roster(5)]})
    expect(skirmish.canAlignRoles).toBe(false)
    expect(skirmish.groups.map(team => matchGridColumns(team.players.length).max)).toEqual([2, 5])
  })

  it('preserves partial or missing team evidence without inventing opposing sides', () => {
    expect(resolveMatchLayout({game: 'VALORANT', teams: []})).toEqual({kind: 'roster', groups: [], canAlignRoles: false})
    expect(resolveMatchLayout({game: 'VALORANT', mode: 'Deathmatch', teams: []}).groups).toEqual([])
    const players = roster(10)
    expect(resolveMatchLayout({game: 'VALORANT', teams: [players]})).toEqual({kind: 'roster', groups: [players], canAlignRoles: false})
    expect(resolveMatchLayout({game: 'VALORANT', teams: [roster(0), roster(0)]}).canAlignRoles).toBe(false)
    expect(resolveMatchLayout({game: 'VALORANT', teams: [roster(6), roster(6)]}).canAlignRoles).toBe(false)
  })

  it('does not mutate frozen teams, lose repeated anonymous names, or reorder players', () => {
    const duplicate = {name: 'Hidden player', hidden: true}
    const players = Object.freeze([duplicate, {...duplicate}])
    const team = Object.freeze({name: 'Unknown', players})
    const teams = Object.freeze([team]) as unknown as readonly MatchTeam[]
    const layout = resolveMatchLayout({game: 'VALORANT', freeForAll: true, teams})
    expect(layout.groups[0].players).toHaveLength(2)
    expect(layout.groups[0].players[0]).toBe(duplicate)
    expect(team.players).toBe(players)
  })
})

describe('responsive roster grid columns', () => {
  it('balances a TFT field across two four-player rows without changing other free-for-all grids', () => {
    expect(matchGridColumns(8, 'Teamfight Tactics')).toEqual({minWidth: 180, max: 4, repeat: 'fit'})
    expect(matchGridColumns(2, 'Teamfight Tactics').max).toBe(2)
    expect(matchGridColumns(8, 'VALORANT').max).toBe(6)
    expect(matchGridColumns(14, 'VALORANT').max).toBe(6)
  })

  it.each([[0, 1], [1, 1], [2, 2], [3, 3], [5, 5], [6, 6], [16, 6], [-1, 1], [NaN, 1], [Infinity, 1]])('caps %s participants at %s columns', (count, columns) => {
    expect(matchGridColumns(count)).toEqual({minWidth: 180, max: columns, repeat: 'fit'})
  })
})
