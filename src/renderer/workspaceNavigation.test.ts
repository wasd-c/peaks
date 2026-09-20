import {describe, expect, it} from 'vitest'
import {initialWorkspaceNavigation, workspaceNavigation} from './workspaceNavigation'
import type {MatchSelection} from './matchReportRefresh'
import type {Player} from './types'

const selection: MatchSelection = {accountId: 'owner', region: 'EU', match: {id: 'one', game: 'VALORANT', result: 'Win'}}
const player: Player = {id: 'player', riotId: 'Visitor#TEST', region: 'EUW'}

describe('workspace return path', () => {
  it('returns through report, player profile, and nested report without losing their sources', () => {
    let state = workspaceNavigation(initialWorkspaceNavigation, {type: 'match', selection})
    state = workspaceNavigation(state, {type: 'player', player})
    const publicReport = {...selection, source: 'player-profile' as const}
    state = workspaceNavigation(state, {type: 'match', selection: publicReport})
    expect(state.routes.at(-1)).toMatchObject({kind: 'match', selection: publicReport})
    state = workspaceNavigation(state, {type: 'back'})
    expect(state.routes.at(-1)).toMatchObject({kind: 'player', player})
    state = workspaceNavigation(state, {type: 'back'})
    expect(state.routes.at(-1)).toMatchObject({kind: 'match', selection})
    expect(workspaceNavigation(state, {type: 'back'}).routes).toEqual([])
  })
  it('gives repeated visits distinct keys and drops the return path when changing the main page', () => {
    let state = workspaceNavigation(initialWorkspaceNavigation, {type: 'player', player})
    const first = state.routes[0].key
    state = workspaceNavigation(state, {type: 'match', selection})
    state = workspaceNavigation(state, {type: 'player', player})
    expect(state.routes.at(-1)?.key).not.toBe(first)
    state = workspaceNavigation(state, {type: 'reset'})
    expect(state.routes).toEqual([])
    expect(workspaceNavigation(state, {type: 'back'}).routes).toEqual([])
  })
})
