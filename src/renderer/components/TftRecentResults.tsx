import {Button, Grid, Heading, HStack, Text, Tooltip, VStack} from '../ui'
import {formatNumber, localeTags, t, useLocale} from '../i18n'
import {gameMode} from '../riotProfile'
import {tftRecentResults} from '../tftRecentResults'
import type {Account, Match} from '../types'
import {StreakFlame} from './StreakFlame'

function StreakFrost() {
  return <svg className="pd-tft-streak__effect pd-tft-streak__frost" viewBox="0 0 100 120" aria-hidden focusable="false">
    <g fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M23 22V57M8 31L38 48M8 48L38 31M23 22L18 28M23 22L28 28M23 57L18 51M23 57L28 51M8 31L16 31M8 31L12 39M38 48L30 48M38 48L34 40M8 48L12 40M8 48L16 48M38 31L30 31M38 31L34 39" />
      <path d="M79 70V105M64 79L94 96M64 96L94 79M79 70L74 76M79 70L84 76M79 105L74 99M79 105L84 99M64 79L72 79M64 79L68 87M94 96L86 96M94 96L90 88M64 96L68 88M64 96L72 96M94 79L86 79M94 79L90 87" />
      <path d="M62 25L68 13L72 30L84 23L78 39M26 82L18 93L25 108L31 96M41 104L49 115L59 109" />
    </g>
  </svg>
}

export function TftRecentResults({account, mode = 'all', onSelectMatch}: {account: Account; mode?: string; onSelectMatch: (match: Match) => void}) {
  const locale = useLocale()
  const matches = (account.matches ?? []).filter(match => mode === 'all' || (mode === 'solo' ? gameMode(match) !== 'Double Up' : gameMode(match) === mode))
  const {rows, streak} = tftRecentResults(matches, account.riotId)
  const effect = streak != null && streak >= 2 ? 'fire' : streak != null && streak <= -2 ? 'frost' : 'none'
  const date = new Intl.DateTimeFormat(localeTags[locale], {dateStyle: 'medium', timeStyle: 'short'})
  const streakLabel = `${t('Current streak')} · ${streak == null ? '—' : `${t(streak > 0 ? 'Win' : 'Loss')} · ${formatNumber(Math.abs(streak))}`}`
  if (!rows.length) return null
  return <VStack gap={3}>
    <HStack justify="between" align="center" gap={2} wrap="wrap">
      <Heading level={3}>{t('Recent matches')}{mode === 'all' ? ` · ${t('All modes')}` : ''}</Heading>
      <Text type="supporting">{t('{{count}} of up to 20 matches', {count: rows.length})}</Text>
    </HStack>
    <HStack className="pd-tft-recent" gap={4} align="center">
      <Tooltip content={streakLabel}>
        <VStack className="pd-tft-streak" data-effect={effect} align="center" gap={0} role="img" aria-label={streakLabel}>
          <HStack className="pd-tft-streak__stage" align="center" justify="center">
            {effect === 'fire' ? <StreakFlame /> : effect === 'frost' ? <StreakFrost /> : null}
            <Text className="pd-tft-streak__value" type="display-2" hasTabularNumbers aria-hidden>{streak == null ? '—' : formatNumber(streak)}</Text>
          </HStack>
          <Text className="pd-tft-streak__label" type="supporting" aria-hidden>{t('Streak')}</Text>
        </VStack>
      </Tooltip>
      <Grid className="pd-tft-recent__grid" columns={10} width="max-content" justify="start" gap={1.5} role="group" aria-label={t('TFT match history')}>
        {rows.map(({match, placement}, index) => {
          const label = `${placement == null ? t('Placement unavailable') : `#${placement}`} · ${date.format(match.playedAtTimestamp!)} · ${t('View match')}`
          return <Button key={match.id ?? `${match.playedAtTimestamp}-${index}`} className="pd-tft-recent__placement" data-placement={placement ?? 'unknown'} label={label} tooltip={label} size="sm" width="max-content" variant="ghost" onClick={() => onSelectMatch(match)}
            style={placement == null ? undefined : {backgroundColor: `var(--color-tft-place-${placement})`, color: `var(--color-tft-place-${placement === 1 ? 'gold' : placement <= 4 ? 'silver' : 'white'})`}}>
            <Text className="pd-tft-recent__place-label" data-metal={placement === 1 ? 'gold' : placement != null && placement <= 4 ? 'silver' : 'none'} color="inherit" weight="bold" hasTabularNumbers aria-hidden>{placement == null ? '—' : `#${placement}`}</Text>
          </Button>
        })}
      </Grid>
    </HStack>
  </VStack>
}
