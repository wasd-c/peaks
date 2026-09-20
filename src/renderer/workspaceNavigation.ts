import type {MatchSelection} from './matchReportRefresh'
import type {Player} from './types'

export type WorkspaceRoute = {key: string; kind: 'match'; selection: MatchSelection} | {key: string; kind: 'player'; player: Player}
export interface WorkspaceNavigation {nextKey: number; routes: WorkspaceRoute[]}
export type WorkspaceNavigationAction = {type: 'match'; selection: MatchSelection} | {type: 'player'; player: Player} | {type: 'back'} | {type: 'reset'}
export const initialWorkspaceNavigation: WorkspaceNavigation = {nextKey: 1, routes: []}

/** Reports and consulted profiles unwind in the order they were opened. */
export function workspaceNavigation(state: WorkspaceNavigation, action: WorkspaceNavigationAction): WorkspaceNavigation {
  if (action.type === 'reset') return {...state, routes: []}
  if (action.type === 'back') return {...state, routes: state.routes.slice(0, -1)}
  const key = `detail-${state.nextKey}`
  const route: WorkspaceRoute = action.type === 'match' ? {key, kind: 'match', selection: action.selection} : {key, kind: 'player', player: action.player}
  return {nextKey: state.nextKey + 1, routes: [...state.routes, route]}
}
