import type {Game} from './types'
import valorantIndex from '../peaks/ui/assets/riot/valorant/index.json'

const bundledAssets = import.meta.glob<string>(
  [
    '../peaks/ui/assets/riot/**/*.png',
    '../peaks/ui/assets/*.png',
    '../peaks/ui/assets/*.svg',
  ],
  {eager: true, import: 'default', query: '?url'},
)

const slug = (value: string) => value
  .normalize('NFKD')
  .replace(/[\u0300-\u036f]/g, '')
  .toLowerCase()
  .replace(/[^a-z0-9]+/g, '-')
  .replace(/^-|-$/g, '')

export const localAsset = (path: string) => {
  const normalized = path.replace(/^\.\//, '')
  const sourcePath = `../peaks/ui/assets/${normalized}`
  const asset = bundledAssets[sourcePath]
  if (!asset) throw new Error(`Missing bundled local asset: ${normalized}`)
  return asset
}

const VALORANT_RANK_KEYS = new Set([
  'unranked',
  ...[
    'iron',
    'bronze',
    'silver',
    'gold',
    'platinum',
    'diamond',
    'ascendant',
    'immortal',
  ].flatMap(tier => [1, 2, 3].map(division => `${tier}-${division}`)),
  'radiant',
])

export const hasExactValorantRankAsset = (rank?: string) => (
  VALORANT_RANK_KEYS.has(slug(rank || 'unranked'))
)

export const valorantRankAsset = (rank?: string) => {
  const key = slug(rank || 'unranked')
  const resolved = VALORANT_RANK_KEYS.has(key) ? key : 'unranked'
  return localAsset(`riot/valorant/ranks/${resolved}.png`)
}

export const rankAsset = (game: Game, tier: string) => {
  if (game === 'VALORANT') return valorantRankAsset(tier)
  const folder = game === 'Teamfight Tactics' ? 'tft' : 'lol'
  return localAsset(`riot/${folder}/ranks/${slug(tier.split(' ')[0] || 'unranked')}.png`)
}

const sameIdentity = (left: string, right: string) => (
  left.localeCompare(right, undefined, {sensitivity: 'base'}) === 0
)

const valorantAgentEntry = (agent?: string) => (
  agent
    ? valorantIndex.agents.find(item => (
        sameIdentity(item.displayName, agent) || sameIdentity(item.uuid, agent)
      ))
    : undefined
)

export const valorantAgentName = (agent?: string) => (
  valorantAgentEntry(agent)?.displayName ?? agent
)

export const valorantAgentAsset = (agent?: string) => {
  const entry = valorantAgentEntry(agent)
  return entry ? localAsset(`riot/${entry.path}`) : undefined
}

/** Transparent full-body game artwork, bundled locally for player cards. */
export const valorantAgentPortraitAsset = (agent?: string) => {
  const entry = valorantAgentEntry(agent)
  return entry ? localAsset(`riot/${entry.portraitPath}`) : undefined
}

const valorantMapEntry = (map?: string) => (
  map
    ? valorantIndex.maps.find(item => {
        const internalName = item.mapUrl.split('/').filter(Boolean).at(-1)
        return sameIdentity(item.displayName, map)
          || sameIdentity(item.uuid, map)
          || sameIdentity(item.mapUrl, map)
          || Boolean(internalName && sameIdentity(internalName, map))
      })
    : undefined
)

export const valorantMapName = (map?: string) => (
  valorantMapEntry(map)?.displayName ?? map ?? 'Unknown map'
)

export const valorantMapAsset = (map?: string) => {
  const entry = valorantMapEntry(map)
  return entry
    ? localAsset(`riot/${entry.path}`)
    : localAsset('riot/artwork/valorant-ascent.png')
}

export const gameArtwork = (game?: Game, map?: string) => {
  if (game === 'VALORANT') return valorantMapAsset(map)
  if (game === 'Teamfight Tactics') return localAsset('riot/artwork/tft-default-arena.png')
  return localAsset('riot/artwork/lol-summoners-rift.png')
}
