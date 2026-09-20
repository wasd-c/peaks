import {EmptyState} from '@astryxdesign/core/EmptyState'
import {Heading} from '@astryxdesign/core/Heading'
import {HStack} from '@astryxdesign/core/HStack'
import {Icon} from '@astryxdesign/core/Icon'
import {Item} from '@astryxdesign/core/Item'
import {List} from '@astryxdesign/core/List'
import {Text} from '@astryxdesign/core/Text'
import {Tooltip} from '@astryxdesign/core/Tooltip'
import {VStack} from '@astryxdesign/core/VStack'
import {Theme} from '@astryxdesign/core/theme'
import {Gamepad2} from 'lucide-react'
import {hasExactValorantRankAsset, rankAsset} from '../assets'
import {displayText, t, useLocale} from '../i18n'
import {matchHistoryRow} from '../matchHistoryRow'
import {gameProfileIcon} from '../profileAssets'
import {profileTheme} from '../theme/profileThemes'
import type {Game, Match} from '../types'

function rankImage(game: Game, rank?: string) {
  if (!rank) return undefined
  const known = game === 'VALORANT' ? hasExactValorantRankAsset(rank)
    : ['iron', 'bronze', 'silver', 'gold', 'platinum', 'emerald', 'diamond', 'master', 'grandmaster', 'challenger'].includes(rank.toLowerCase().split(' ')[0])
  return known ? rankAsset(game, rank) : undefined
}

export function MatchHistoryList({matches, riotId, heading = 'Recent matches', onSelect}: {
  matches: Match[]
  riotId?: string
  heading?: string | null
  onSelect?: (match: Match) => void
}) {
  useLocale()
  if (!matches.length) return <EmptyState icon={<Icon icon={Gamepad2} color="secondary" />} title={t('No recent matches')} />
  return <Theme theme={profileTheme('riot')}>
    <List className="peaks-dense-list peaks-match-list pd-match-history" density="compact"
      aria-label={displayText(heading ?? 'Recent matches')}
      header={heading ? <Heading level={2}>{displayText(heading)}</Heading> : undefined}>
      {matches.map((match, index) => {
        const row = matchHistoryRow(match, riotId)
        const isTft = match.game === 'Teamfight Tactics'
        const emblem = rankImage(match.game, row.rank)
        const media = <HStack className="pd-match-history__media" align="center" justify="center" gap={0}>
          <img className="pd-match-history__game" src={gameProfileIcon(match.game)} alt={match.game} />
          {row.character && !isTft ? <img className="pd-match-history__character" src={row.character.image} alt="" /> : null}
        </HStack>
        return <Item as="li" className="pd-match-history__row" key={match.id ?? `${match.game}-${index}`}
          onClick={onSelect ? () => onSelect(match) : undefined}
          startContent={row.character && !isTft ? <Tooltip content={row.character.name} hasHoverIndication={false}>{media}</Tooltip> : media}
          label={<HStack className="pd-match-history__content" align="center" gap={5} wrap="wrap">
            {isTft ? <Text className="pd-match-history__placement" hasTabularNumbers weight="semibold" data-placement={row.placement ?? 'unknown'}
              style={row.placement == null ? undefined : {backgroundColor: `var(--color-tft-place-${row.placement})`, color: `var(--color-tft-place-${row.placement === 1 ? 'gold' : row.placement <= 4 ? 'silver' : 'white'})`}}>
              <Text className="pd-tft-recent__place-label" color="inherit" weight="bold" hasTabularNumbers data-metal={row.placement === 1 ? 'gold' : row.placement != null && row.placement <= 4 ? 'silver' : 'none'}>
                {row.placement == null ? '—' : `#${row.placement}`}
              </Text>
            </Text> : <VStack className="pd-match-history__result" gap={0.5}>
              <Text weight="semibold" data-result={row.result}>{row.result === 'Unknown' ? '—' : t(row.result)}</Text>
              {row.score ? <Text hasTabularNumbers type="supporting" color="secondary">{row.score}</Text> : null}
            </VStack>}
            {row.rank || row.delta != null ? <HStack className="pd-match-history__rating" align="center" gap={2}>
              {emblem ? <img className="pd-match-history__rank" src={emblem} alt="" /> : null}
              {row.rank ? <Text type="supporting">{displayText(row.rank)}</Text> : null}
              {row.delta != null ? <Text className="pd-match-history__delta" hasTabularNumbers weight="semibold"
                data-direction={row.delta > 0 ? 'gain' : row.delta < 0 ? 'loss' : 'neutral'}
                aria-label={`${row.delta > 0 ? '+' : ''}${row.delta} ${row.deltaUnit ?? ''}`.trim()}>
                {row.delta > 0 ? '+' : ''}{row.delta}
              </Text> : null}
            </HStack> : null}
          </HStack>} />
      })}
    </List>
  </Theme>
}
