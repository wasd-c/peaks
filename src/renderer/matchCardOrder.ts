import valorantIndex from '../peaks/ui/assets/riot/valorant/index.json'
import type {MatchPlayer} from './types'

export type ValorantCardRole = 'space-duelist' | 'ego-duelist' | 'initiator' | 'controller' | 'sentinel'

// Official roles come from Riot's agent roster. The two duelist groups are a
// presentation choice: movement/infiltration entries versus isolated fights.
const ROLE_AGENTS: Record<ValorantCardRole, readonly string[]> = {
  'space-duelist': ['Jett', 'Raze', 'Neon', 'Waylay', 'Yoru'],
  'ego-duelist': ['Phoenix', 'Reyna', 'Iso'],
  initiator: ['Breach', 'Sova', 'Skye', 'KAY/O', 'Fade', 'Gekko', 'Tejo'],
  controller: ['Brimstone', 'Viper', 'Omen', 'Astra', 'Harbor', 'Clove', 'Miks'],
  sentinel: ['Sage', 'Cypher', 'Killjoy', 'Chamber', 'Deadlock', 'Vyse', 'Veto'],
}
const ROLE_ORDER = Object.keys(ROLE_AGENTS) as ValorantCardRole[]
const normalize = (value: string) => value.trim().toLowerCase().replace(/[^a-z0-9]/g, '')
const rolesByName = new Map(Object.entries(ROLE_AGENTS).flatMap(([role, names]) => names.map(name => [normalize(name), role as ValorantCardRole] as const)))
const agents = new Map(valorantIndex.agents.flatMap(agent => [agent.displayName, agent.uuid].map(alias => [normalize(alias), {
  name: agent.displayName,
  role: rolesByName.get(normalize(agent.displayName)),
}] as const)))
const resolveAgent = (value?: string) => value ? agents.get(normalize(value)) : undefined

export const valorantCardRole = (agent?: string): ValorantCardRole | undefined => resolveAgent(agent)?.role

const roleOrder = (player: MatchPlayer) => {
  const role = valorantCardRole(player.agent)
  return role ? ROLE_ORDER.indexOf(role) : ROLE_ORDER.length
}
const isDuelist = (role?: ValorantCardRole) => role === 'space-duelist' || role === 'ego-duelist'
type PairingScore = [exactRoles: number, duelistPairs: number, sameAgents: number, stability: number]

function scorePairing(anchor: readonly MatchPlayer[], opponents: readonly MatchPlayer[], order: readonly number[]): PairingScore {
  const score: PairingScore = [0, 0, 0, 0]
  order.forEach((originalIndex, column) => {
    score[3] -= Math.abs(originalIndex - column)
    const left = resolveAgent(anchor[column]?.agent)
    const right = resolveAgent(opponents[originalIndex].agent)
    if (!left || !right) return
    if (left.role && left.role === right.role) score[0]++
    if (isDuelist(left.role) && isDuelist(right.role)) score[1]++
    if (left.name === right.name) score[2]++
  })
  return score
}

function betterThan(left: PairingScore, right: PairingScore) {
  for (let index = 0; index < left.length; index++) {
    if (left[index] !== right[index]) return left[index] > right[index]
  }
  return false
}

/**
 * Align opposing columns without sacrificing a possible role match to an early
 * greedy choice. Five players need only 120 assignments. Partial rosters use
 * the shorter side as the anchor, keeping every available match visible.
 */
export function alignValorantMatchup(first: readonly MatchPlayer[], second: readonly MatchPlayer[]): [MatchPlayer[], MatchPlayer[]] {
  if (!first.length || !second.length || first.length > 5 || second.length > 5) return [[...first], [...second]]
  const anchorIsFirst = first.length <= second.length
  const anchor = [...(anchorIsFirst ? first : second)].sort((left, right) => roleOrder(left) - roleOrder(right))
  const opponents = anchorIsFirst ? second : first
  let bestOrder = opponents.map((_, index) => index)
  let bestScore = scorePairing(anchor, opponents, bestOrder)
  const search = (order: number[], remaining: number[]) => {
    if (!remaining.length) {
      const score = scorePairing(anchor, opponents, order)
      if (betterThan(score, bestScore)) { bestScore = score; bestOrder = [...order] }
      return
    }
    for (const index of remaining) search([...order, index], remaining.filter(candidate => candidate !== index))
  }
  search([], bestOrder)
  const aligned = bestOrder.map(index => opponents[index])
  return anchorIsFirst ? [anchor, aligned] : [aligned, anchor]
}

/** Reorder a single roster; crossing a team boundary is never a valid move. */
export function moveTeamCard<T>(teams: readonly (readonly T[])[], from: {team: number; index: number}, to: {team: number; index: number}): T[][] {
  const result = teams.map(team => [...team])
  if (from.team !== to.team || !Number.isInteger(from.team) || !Number.isInteger(from.index) || !Number.isInteger(to.index)) return result
  const roster = result[from.team]
  if (!roster || from.index < 0 || to.index < 0 || from.index >= roster.length || to.index >= roster.length) return result
  const [player] = roster.splice(from.index, 1)
  roster.splice(to.index, 0, player)
  return result
}
