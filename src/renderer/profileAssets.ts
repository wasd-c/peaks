import type {CSSProperties} from 'react'
import {accountGameIcon, findAccountIcon} from './accountIcons'
import {getLanguage} from './i18n'
import type {Game} from './types'
import catalog from './assets/profiles/tft.json'
import sets from './assets/profiles/tft-sets.json'

const images = import.meta.glob<string>('./assets/profiles/**/*.{webp,png,svg}', {eager: true, import: 'default', query: '?url'})
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
export const tftUnitCost = (id: string) => setUnit(id)?.cost
export const tftAssetLabel = (kind: TftAssetKind, id: string) => {
  const modern = kind === 'champion' ? setUnit(id) : kind === 'trait' ? (sets.traits as Record<string, {names: Record<string, string>}>)[id] : undefined
  return modern?.names[getLanguage()] ?? modern?.names.en ?? entry(kind, id)?.names[getLanguage()] ?? entry(kind, id)?.names.en ?? id
}
export const tftUnitPortrait = (id: string) => {
  const unit = setUnit(id)
  return unit?.image ? images[`./assets/profiles/${unit.image}`] : undefined
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
