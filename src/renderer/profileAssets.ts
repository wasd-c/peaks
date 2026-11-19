import type {CSSProperties} from 'react'
import {accountGameIcon, findAccountIcon} from './accountIcons'
import {getLanguage} from './i18n'
import type {Game} from './types'
import catalog from './assets/profiles/tft.json'
import sets from './assets/profiles/tft-sets.json'
import {tftChampionEntry} from './tftCatalog'

const images = import.meta.glob<string>(['./assets/profiles/**/*.{webp,png,svg}', '!./assets/profiles/tft-library/**'], {eager: true, import: 'default', query: '?url'})
// Thousands of archived thumbnails stay separate assets instead of base64 in JS.
const tftImages = import.meta.glob<string>('./assets/profiles/tft-library/*.webp', {eager: true, import: 'default', query: '?url&no-inline'})
export const gameProfileIcon = (game: Game) => game === 'Teamfight Tactics' ? images['./assets/profiles/tft.svg']
  : game === 'League of Legends' ? images['./assets/profiles/league.svg'] : accountGameIcon(game)
export const championArtwork = (id?: string) => {
  const champion = id ? findAccountIcon({game: 'League of Legends', characterId: id}) : undefined
  return champion ? images[`./assets/profiles/champions/${champion.characterId}.webp`] : undefined
}

export type TftAssetKind = 'champion' | 'trait' | 'item' | 'augments'
type Entry = {names: Record<string, string>; sprite: string; x: number; y: number; columns?: number}
const entry = (kind: TftAssetKind, id: string): Entry | undefined => (catalog[kind] as Record<string, Entry>)[id]
type SetUnit = {names: Record<string, string | null>; cost?: number; set: number; image?: string}
const setUnit = (id: string): SetUnit | undefined => (sets.units as Record<string, SetUnit>)[id]
export const tftUnitCost = (id: string, setNumber?: number) => tftChampionEntry(id, setNumber)?.cost ?? (setNumber == null ? setUnit(id)?.cost : undefined)
export const tftAssetLabel = (kind: TftAssetKind, id: string, setNumber?: number) => {
  const modern = kind === 'champion' ? tftChampionEntry(id, setNumber) ?? (setNumber == null ? setUnit(id) : undefined) : kind === 'trait' ? (sets.traits as Record<string, {names: Record<string, string>}>)[id] : undefined
  return modern?.names[getLanguage()] ?? modern?.names.en ?? entry(kind, id)?.names[getLanguage()] ?? entry(kind, id)?.names.en ?? id
}
export const tftProfileImage = (path?: string | null) => path ? images[`./assets/profiles/${path}`] ?? tftImages[`./assets/profiles/${path}`] : undefined
export const tftUnitPortrait = (id: string, setNumber?: number) => {
  // Keep existing portraits at their original resolution when they belong to this set.
  const unit = setUnit(id)
  if (unit?.image && (setNumber == null || setNumber === unit.set)) return tftProfileImage(unit.image)
  return tftProfileImage(tftChampionEntry(id, setNumber)?.portrait)
}
export function tftSpriteStyle(kind: TftAssetKind, id: string): CSSProperties | undefined {
  const row = entry(kind, id)
  const source = row ? images[`./assets/profiles/tft/${row.sprite}`] : undefined
  if (!row || !source || !row.columns) return undefined
  return {
    backgroundImage: `url("${source}")`,
    backgroundSize: `calc(var(--pd-tft-icon-size) * ${row.columns}) auto`,
    backgroundPosition: `calc(var(--pd-tft-icon-size) * ${-row.x / 48}) calc(var(--pd-tft-icon-size) * ${-row.y / 48})`,
  }
}

/** Trait names are aligned by language in each set's champion catalog. Match
 * the exact set first so a reused localized name cannot borrow another icon. */
export function tftChampionTraitStyle(names: string[], setNumber?: number): CSSProperties | undefined {
  const candidates = Object.entries(catalog.trait as Record<string, Entry>).filter(([, row]) =>
    Object.values(row.names).some(name => names.includes(name)))
  const inSet = setNumber == null ? [] : candidates.filter(([id]) => id.startsWith(`TFT${setNumber}_`))
  const selected = inSet.length === 1 ? inSet[0] : candidates.length === 1 ? candidates[0] : undefined
  return selected ? tftSpriteStyle('trait', selected[0]) : undefined
}
