import type {Account, AccountIconSelection} from './types'
import {valorantAgentAsset} from './assets'
import valorantIndex from '../peaks/ui/assets/riot/valorant/index.json'
import accountIconIndex from './assets/account-icons/index.json'

export type AccountIconGame = AccountIconSelection['game']

export interface AccountIconOption extends AccountIconSelection {
  name: string
  image: string
  names?: {en: string; fr: string; ko: string}
}

const bundledImages = import.meta.glob<string>(
  ['./assets/account-icons/**/*.png', './assets/account-icons/*.svg'],
  {eager: true, import: 'default', query: '?url'},
)

function iconImage(path: string): string {
  const image = bundledImages[`./assets/account-icons/${path}`]
  if (!image) throw new Error(`Missing bundled account artwork: ${path}`)
  return image
}

const valorantOptions: AccountIconOption[] = valorantIndex.agents.map<AccountIconOption>(agent => ({
  game: 'VALORANT',
  characterId: agent.uuid,
  name: agent.displayName,
  image: valorantAgentAsset(agent.uuid)!,
})).sort((left, right) => left.name.localeCompare(right.name, 'en'))

const leagueOptions: AccountIconOption[] = accountIconIndex.champions.map(champion => ({
  game: 'League of Legends',
  characterId: champion.id,
  name: champion.name,
  names: champion.names,
  image: iconImage(champion.path),
}))

/** Fully bundled, alphabetical character roster for the two picker tabs. */
export function accountIconOptions(game: AccountIconGame): readonly AccountIconOption[] {
  return game === 'VALORANT' ? valorantOptions : leagueOptions
}

export function accountGameIcon(game: AccountIconGame): string {
  return iconImage(game === 'VALORANT' ? 'valorant.png' : 'league.svg')
}

function identity(value: string): string {
  return value.normalize('NFKC').trim().toLocaleLowerCase('en')
}

/** Names and numeric League IDs from client histories resolve to stable saved IDs. */
export function findAccountIcon(selection?: AccountIconSelection | null): AccountIconOption | undefined {
  if (!selection) return undefined
  const key = identity(selection.characterId)
  const options = accountIconOptions(selection.game)
  const direct = options.find(option => identity(option.characterId) === key
    || identity(option.name) === key
    || Object.values(option.names ?? {}).some(name => identity(name) === key))
  if (direct || selection.game === 'VALORANT') return direct
  const champion = accountIconIndex.champions.find(item => item.key === key)
  return champion ? leagueOptions.find(option => option.characterId === champion.id) : undefined
}

/**
 * Manual choice wins. Otherwise compare canonical timestamps across games;
 * preserve provider order for legacy rows with no timestamp, after dated rows.
 * Relative display labels never establish chronology. Unknowns stay neutral.
 */
export function resolveAccountIcon(account: Pick<Account, 'accountIcon' | 'matches' | 'riotId'>): AccountIconOption | undefined {
  const manual = findAccountIcon(account.accountIcon)
  if (manual) return manual
  const timestamp = (value?: number) => typeof value === 'number' && Number.isFinite(value) && value > 0 ? value : 0
  const match = account.matches?.filter(item => item.game === 'VALORANT' || item.game === 'League of Legends')
    .sort((left, right) => timestamp(right.playedAtTimestamp) - timestamp(left.playedAtTimestamp))[0]
  if (!match || (match.game !== 'VALORANT' && match.game !== 'League of Legends')) return undefined
  const self = match.teams?.flatMap(team => team.players).find(player => player.self && !player.hidden)
    ?? match.teams?.flatMap(team => team.players).find(player => !player.hidden
      && identity(player.riotId ?? player.name) === identity(account.riotId))
  const character = match.agent || self?.agent
  return character ? findAccountIcon({game: match.game, characterId: character}) : undefined
}
