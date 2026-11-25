import {hasExactValorantRankAsset, rankAsset} from '../assets'
import {displayText, useLocale} from '../i18n'
import type {Game} from '../types'
import {Tooltip} from '../ui'
import './accountRankEmblem.css'

const valorantTiers = ['Iron', 'Bronze', 'Silver', 'Gold', 'Platinum', 'Diamond', 'Ascendant', 'Immortal']
const leagueRank = /^(iron|bronze|silver|gold|platinum|emerald|diamond|master|grandmaster|challenger)(?:\s+(IV|III|II|I|[1-4]))?$/i

function valorantLabel(rank: string, tierId?: number) {
  const label = rank.replace(/\s+(I{1,3})$/i, (_, division: string) => ` ${division.length}`)
  if (label && hasExactValorantRankAsset(label)) return label
  // Some reports supply only the verified numeric tier or omit the division name.
  if (!rank && tierId === 27) return 'Radiant'
  if (tierId != null && Number.isInteger(tierId) && tierId >= 3 && tierId <= 26) {
    const tier = valorantTiers[Math.floor((tierId - 3) / 3)]
    if (!rank || tier.toLowerCase() === rank.toLowerCase()) return `${tier} ${(tierId - 3) % 3 + 1}`
  }
  return rank
}

export function AccountRankEmblem({game, rank, tierId}: {game: Game; rank?: string; tierId?: number}) {
  useLocale()
  const name = (rank ?? '').trim().replace(/^(unknown|unavailable|rank unavailable|—|-)$/i, '')
  const label = game === 'VALORANT' ? valorantLabel(name, tierId) : name
  if (!label) return null
  const league = game !== 'VALORANT' && leagueRank.exec(label)
  if (!league && !(game === 'VALORANT' && hasExactValorantRankAsset(label))) return <span>{displayText(label)}</span>
  const localized = displayText(label)
  return <Tooltip content={localized}>
    <span className="account-rank-emblem" role="img" aria-label={localized}>
      <img src={rankAsset(game, label)} alt="" />
      {league && league[2] ? <small>{league[2].toUpperCase()}</small> : null}
    </span>
  </Tooltip>
}
