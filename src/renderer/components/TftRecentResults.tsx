import {Button} from '@astryxdesign/core/Button'
import {Grid} from '@astryxdesign/core/Grid'
import {Heading} from '@astryxdesign/core/Heading'
import {HStack} from '@astryxdesign/core/HStack'
import {Text} from '@astryxdesign/core/Text'
import {Tooltip} from '@astryxdesign/core/Tooltip'
import {VStack} from '@astryxdesign/core/VStack'
import {formatNumber, localeTags, t, useLocale} from '../i18n'
import {gameMode} from '../riotProfile'
import {tftRecentResults} from '../tftRecentResults'
import type {Account, Match} from '../types'

function StreakFlame() {
  return <svg className="pd-tft-streak__effect pd-tft-streak__flame" viewBox="0 0 100 120" aria-hidden focusable="false">
    <path className="pd-tft-streak__flame-outer" d="M50 113C24 113 10 98 14 78C17 63 26 56 25 42C35 46 36 56 37 64C48 49 43 27 57 8C55 30 72 39 68 60C73 56 77 49 76 41C95 67 96 87 83 101C74 111 62 114 50 113Z" />
    <path className="pd-tft-streak__flame-middle" d="M51 112C32 110 26 100 29 85C31 76 39 70 40 59C49 67 48 75 49 79C58 69 64 54 60 40C81 63 85 88 73 103C67 110 60 112 51 112Z" />
    <path className="pd-tft-streak__flame-core" d="M51 111C41 109 37 102 40 94C43 86 52 81 54 71C66 85 69 98 61 107C58 110 55 111 51 111Z" />
    <g className="pd-tft-streak__sparks">
      <circle className="pd-tft-streak__spark" cx="26" cy="57" r="2" />
      <circle className="pd-tft-streak__spark" cx="73" cy="47" r="1.5" />
      <circle className="pd-tft-streak__spark" cx="48" cy="34" r="1.5" />
    </g>
  </svg>
}

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
    <Heading level={3}>{t('Last 20 games')}</Heading>
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
