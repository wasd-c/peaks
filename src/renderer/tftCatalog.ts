import index from './data/tft/index.json'

export type TftScaling = 'ap' | 'ad' | 'health' | 'armor' | 'mr' | 'speed' | 'mana'
export type TftCalculation = {__type?: string; [key: string]: unknown}
export interface TftChampion {
  names: Record<string, string | null>
  cost?: number
  role?: string | null
  portrait?: string | null
  traits: Record<string, string[]>
  stats: Record<string, number | null>
  ability: {
    names: Record<string, string>
    descriptions: Record<string, string>
    icon?: string | null
    variables: Record<string, number[]>
    calculations: Record<string, TftCalculation>
    source?: {provider: string; patch: string; generated: string; url: string}
  }
}
export interface TftChampionEntry {
  set: number
  variant: string
  names: TftChampion['names']
  cost?: number
  portrait?: string | null
}
interface TftSet {
  number: number
  defaultVariant: string
  variants: Record<string, {alias?: string; patch?: string; units?: Record<string, TftChampion>}>
}
const entries = index.units as Record<string, Record<string, TftChampionEntry>>
const sets = import.meta.glob<TftSet>('./data/tft/sets/*.json', {import: 'default'})
const loaded = new Map<number, Promise<TftSet>>()

/** Exact Riot ID + set, never a champion-name/suffix match across sets. */
export function tftChampionEntry(id: string, setNumber?: number): TftChampionEntry | undefined {
  const versions = entries[id]
  if (!versions) return undefined
  if (setNumber != null) return versions[String(setNumber)]
  const identifiedSet = /^TFT(\d+)_/.exec(id)?.[1]
  if (identifiedSet && versions[identifiedSet]) return versions[identifiedSet]
  const candidates = Object.values(versions)
  return candidates.length === 1 ? candidates[0] : undefined
}

export async function loadTftChampion(id: string, setNumber?: number, variant?: string): Promise<TftChampion | undefined> {
  const entry = tftChampionEntry(id, setNumber)
  if (!entry) return undefined
  const loader = sets[`./data/tft/sets/${entry.set}.json`]
  if (!loader) return undefined
  let pending = loaded.get(entry.set)
  if (!pending) {
    pending = loader().catch(error => { loaded.delete(entry.set); throw error })
    loaded.set(entry.set, pending)
  }
  const catalog = await pending
  const fromVariant = (key: string) => {
    let roster = catalog.variants[key]
    if (roster?.alias) roster = catalog.variants[roster.alias]
    return roster?.units?.[id]
  }
  // Half-sets can reuse the same core name after removing a champion. Its exact
  // ID still resolves to the archived roster of this set, never a different set.
  return (variant ? fromVariant(variant) : undefined) ?? fromVariant(entry.variant)
}
