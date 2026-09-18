import {t} from './i18n'
import type {Account, Game} from './types'

const leagueRegions = new Set(['BR', 'EUNE', 'EUW', 'JP', 'KR', 'LAN', 'LAS', 'ME', 'NA', 'OCE', 'PH', 'RU', 'SG', 'TH', 'TR', 'TW', 'VN'])
const valorantRegions = new Set(['AP', 'BR', 'EU', 'KR', 'LATAM', 'NA', 'PBE'])

export function accountRegionForGame(account: Account, game: Game): string | undefined {
  const valorant = game === 'VALORANT'
  const value = (valorant ? account.valorantRegion : account.leagueRegion ?? account.region)?.toUpperCase()
  return value && (valorant ? valorantRegions : leagueRegions).has(value) ? value : undefined
}

export function accountRegionLabels(account: Account): string[] {
  const league = accountRegionForGame(account, 'League of Legends')
  const valorant = accountRegionForGame(account, 'VALORANT')
  const labels = [league && `LoL/TFT: ${league}`, valorant && `VALORANT: ${valorant}`].filter((value): value is string => Boolean(value))
  return labels.length ? labels : [t('Region not detected')]
}

export function accountRegionLabel(account: Account): string {
  return accountRegionLabels(account).join(' · ')
}
