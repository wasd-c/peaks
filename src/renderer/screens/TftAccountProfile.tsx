import {useId, useState} from 'react'
import {Button} from '@astryxdesign/core/Button'
import {EmptyState} from '@astryxdesign/core/EmptyState'
import {Grid} from '@astryxdesign/core/Grid'
import {Heading} from '@astryxdesign/core/Heading'
import {HStack} from '@astryxdesign/core/HStack'
import {ProgressBar} from '@astryxdesign/core/ProgressBar'
import {Section} from '@astryxdesign/core/Section'
import {Selector} from '@astryxdesign/core/Selector'
import {Text} from '@astryxdesign/core/Text'
import {Token} from '@astryxdesign/core/Token'
import {Tooltip} from '@astryxdesign/core/Tooltip'
import {VStack} from '@astryxdesign/core/VStack'
import {profileMatches, profilePlayer} from '../accountProfile'
import {displayText, formatNumber, t, useLocale} from '../i18n'
import {tftAssetLabel, tftSpriteStyle, tftUnitCost, tftUnitPortrait, type TftAssetKind} from '../profileAssets'
import {gameMode, tftPositivePlacement, tftSummary} from '../riotProfile'
import type {Account, Match, TftComposition} from '../types'
import {ProfileMetric} from './ValorantAccountProfile'

const number = (value?: number) => value == null ? '—' : formatNumber(value, {maximumFractionDigits: 2})
const percent = (value?: number) => value == null ? '—' : `${number(value)}%`

function TftIcon({kind, id, small = false}: {kind: TftAssetKind; id: string; small?: boolean}) {
  const portrait = kind === 'champion' ? tftUnitPortrait(id) : undefined
  const cost = kind === 'champion' ? tftUnitCost(id) : undefined
  const style = tftSpriteStyle(kind, id)
  if (portrait) return <Tooltip content={`${tftAssetLabel(kind, id)}${cost != null ? ` · ${cost} ${t('gold')}` : ''}`}>
    <img className="pd-tft-unit-portrait" src={portrait} alt={tftAssetLabel(kind, id)} data-cost={cost} style={{borderColor: cost ? `var(--color-tft-cost-${Math.min(cost, 5)})` : undefined}} />
  </Tooltip>
  return <Tooltip content={tftAssetLabel(kind, id)}><HStack className={`pd-tft-icon${small ? ' pd-tft-icon--small' : ''}${kind === 'champion' ? ' pd-tft-icon--champion' : ''}`} style={{...style, ...(kind === 'champion' && cost ? {borderColor: `var(--color-tft-cost-${Math.min(cost, 5)})`} : {})}} role="img" aria-label={tftAssetLabel(kind, id)} align="center" justify="center">
    {!style ? <Text type="supporting">?</Text> : null}
  </HStack></Tooltip>
}

function TftUnitStars({stars}: {stars: number}) {
  const gradientId = useId()
  if (!Number.isInteger(stars) || stars < 1 || stars > 4) return null
  const metal = stars === 1 ? 'bronze' : stars === 2 ? 'silver' : 'gold'
  const positions = stars === 1 ? [[16, 8]] : stars === 2 ? [[8, 8], [24, 8]]
    : stars === 3 ? [[24, 8], [16, 22], [32, 22]] : [[8, 8], [24, 8], [8, 22], [24, 22]]
  return <svg className="pd-tft-unit__stars" data-stars={stars} data-metal={metal} viewBox={`0 0 ${stars === 3 ? 48 : 32} ${stars >= 3 ? 32 : 16}`} aria-hidden focusable="false">
    <defs><linearGradient id={gradientId} x1="0" y1="0" x2="0.4" y2="1">
      <stop offset="0" stopColor={`var(--color-tft-metal-${metal}-light)`} />
      <stop offset="0.3" stopColor={`var(--color-tft-metal-${metal}-highlight)`} />
      <stop offset="0.48" stopColor={`var(--color-tft-metal-${metal}-mid)`} />
      <stop offset="0.68" stopColor={`var(--color-tft-metal-${metal}-light)`} />
      <stop offset="1" stopColor={`var(--color-tft-metal-${metal}-shadow)`} />
    </linearGradient></defs>
    {positions.map(([x, y], index) => <path key={index} className="pd-tft-unit__star" transform={`translate(${x} ${y})`} d="M0-7 2.06-2.83 6.66-2.16 3.33 1.08 4.11 5.66 0 3.5-4.11 5.66-3.33 1.08-6.66-2.16-2.06-2.83Z" fill={`url(#${gradientId})`} stroke="var(--color-background-body)" strokeWidth="1.25" strokeLinejoin="round" />)}
  </svg>
}

export function TftBoard({composition}: {composition?: TftComposition}) {
  if (!composition?.units) return <Text color="secondary" type="supporting">{t('Composition unavailable for this match.')}</Text>
  return <VStack gap={4}>
    <HStack gap={3} align="start" wrap="wrap" role="list" aria-label={t('Final board')}>
      {composition.units.map((unit, index) => <VStack key={`${unit.id}-${index}`} className="pd-tft-unit" gap={1} paddingInlineStart={3} paddingBlockStart={2} align="center" role="listitem" aria-label={t('{{unit}}, {{stars}} stars', {unit: tftAssetLabel('champion', unit.id), stars: unit.stars})}>
        <HStack className="pd-tft-unit__frame" align="center" justify="center">
          <TftIcon kind="champion" id={unit.id} />
          <TftUnitStars stars={unit.stars} />
          {unit.items?.length ? <VStack className="pd-tft-unit__items" gap={0} align="center" role="group" aria-label={t('Equipped items')}>
            {unit.items.map((id, itemIndex) => <TftIcon key={`${id}-${itemIndex}`} kind="item" id={id} small />)}
          </VStack> : null}
        </HStack>
        <Text className="pd-tft-unit-name" type="supporting">{tftAssetLabel('champion', unit.id)}</Text>
      </VStack>)}
    </HStack>
    {composition.traits?.some(trait => trait.tier > 0) ? <HStack gap={3} wrap="wrap" aria-label={t('Active traits')}>
      {composition.traits.filter(trait => trait.tier > 0).sort((a, b) => b.tier - a.tier || b.count - a.count).map(trait => <HStack key={trait.id} gap={1} align="center">
        <TftIcon kind="trait" id={trait.id} small /><Text type="supporting">{tftAssetLabel('trait', trait.id)} · {trait.count}</Text>
      </HStack>)}
    </HStack> : null}
    {composition.augments?.length ? <HStack gap={4} wrap="wrap" aria-label={t('Augments')}>
      {composition.augments.map((id, index) => <HStack key={`${id}-${index}`} align="center" gap={1}><TftIcon kind="augments" id={id} small /><Text type="supporting" color="secondary">{tftAssetLabel('augments', id)}</Text></HStack>)}
    </HStack> : null}
  </VStack>
}

export function TftAccountProfile({account, isSynchronizing, onSelectMatch, mode: controlledMode, onModeChange}: {account: Account; isSynchronizing: boolean; onSelectMatch: (match: Match) => void; mode?: string; onModeChange?: (mode: string) => void}) {
  useLocale()
  const [localMode, setLocalMode] = useState('solo')
  const mode = controlledMode ?? localMode
  const setMode = (value: string) => { setLocalMode(value); onModeChange?.(value) }
  const all = profileMatches(account.matches ?? [], 'Teamfight Tactics')
  const matches = all.filter(match => mode === 'solo' ? gameMode(match) !== 'Double Up' : gameMode(match) === mode)
  const duos = mode === 'Double Up'
  const stats = tftSummary(matches, account.riotId, duos)
  return <VStack gap={5}>
    <HStack gap={4} align="end" justify="between" wrap="wrap">
      <Heading level={3}>{t('Performance & compositions')}</Heading>
      <Selector label={t('Game mode')} value={mode} onChange={setMode} options={[{value: 'solo', label: t('Solo modes')}, ...[...new Set(all.map(gameMode))].map(value => ({value, label: displayText(value)}))]} />
    </HStack>
    {isSynchronizing ? <ProgressBar label={t('Synchronizing match details…')} isIndeterminate /> : null}
    {!matches.length ? <EmptyState title={t('No TFT matches in this selection')} description={t('Open the League client with this Riot account and refresh to load TFT history and final compositions.')}
      actions={<Button label={t('Clear filters')} variant="ghost" onClick={() => setMode('solo')} />} /> : <>
      <Section padding={0} variant="muted"><Grid className="pd-profile-kpis">
        <ProfileMetric prominent label={t('Average placement')} value={number(stats.average)} />
        <ProfileMetric prominent label={stats.positivePlacement === 2 ? t('Top 2 rate') : stats.positivePlacement === 4 ? t('Top 4 rate') : t('Win rate')} value={percent(stats.topRate)} />
        <ProfileMetric prominent label={t('First place rate')} value={percent(stats.winRate)} />
        <ProfileMetric prominent label={t('First places')} value={number(stats.wins)} />
      </Grid></Section>
      <VStack gap={3}>
        <Heading level={3}>{t('Placement distribution')}</Heading>
        <Grid className="pd-tft-placements" gap={3}>{stats.distribution.map(row => <VStack key={row.placement} gap={2}>
          <HStack justify="between"><Text weight="semibold">#{row.placement}</Text><Text color="secondary">{row.count}</Text></HStack>
          <ProgressBar label={t('Placement {{placement}}', {placement: row.placement})} isLabelHidden value={row.count} max={Math.max(stats.detailed, 1)} variant="accent" />
        </VStack>)}</Grid>
      </VStack>
      <Heading level={3}>{t('Match compositions')}</Heading>
      <VStack gap={0} role="list" aria-label={t('TFT match history')}>
        {matches.map((match, index) => {
          const player = profilePlayer(match, account.riotId)
          const placement = player?.stats?.placement
          const positivePlacement = tftPositivePlacement(match)
          return <Section key={match.id ?? index} variant="transparent" padding={0} dividers={['bottom']}>
            <VStack gap={4} paddingBlock={5} role="listitem">
              <HStack gap={4} align="center" justify="between" wrap="wrap">
                <HStack gap={3} align="center">
                  <Token label={placement ? `#${placement}` : '—'} color={placement === 1 ? 'yellow' : placement && positivePlacement != null && placement <= positivePlacement ? 'green' : 'gray'} />
                  <VStack gap={1}><Text weight="semibold">{displayText(gameMode(match))}</Text><Text type="supporting" color="secondary">{displayText(match.playedAt)}{match.durationSeconds ? ` · ${number(match.durationSeconds / 60)} min` : ''}</Text></VStack>
                </HStack>
                <HStack gap={4} align="center" wrap="wrap">
                  <Text color="secondary">{t('Level {{level}}', {level: number(player?.stats?.level)})}</Text>
                  <Text color="secondary">{t('Damage to players')} · {number(player?.stats?.damage)}</Text>
                  <Button label={t('View match')} variant="ghost" size="sm" onClick={() => onSelectMatch(match)} />
                </HStack>
              </HStack>
              <TftBoard composition={player?.composition} />
            </VStack>
          </Section>
        })}
      </VStack>
    </>}
  </VStack>
}
