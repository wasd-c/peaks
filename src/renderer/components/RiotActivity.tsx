import {useMemo, type CSSProperties, type ReactNode} from 'react'
import {Grid} from '@astryxdesign/core/Grid'
import {Heading} from '@astryxdesign/core/Heading'
import {HStack} from '@astryxdesign/core/HStack'
import {Section} from '@astryxdesign/core/Section'
import {Text} from '@astryxdesign/core/Text'
import {Tooltip} from '@astryxdesign/core/Tooltip'
import {VStack} from '@astryxdesign/core/VStack'
import {analyzeActivity, elapsedLabel, GAME_COLORS, recentGameMix} from '../activityAnalytics'
import {formatNumber, localeTags, t, useLocale} from '../i18n'
import {gameProfileIcon} from '../profileAssets'
import {PROFILE_GAMES} from '../riotProfile'
import type {ProfileActivity} from '../types'
import {usePlayerPrivacy} from './PlayerPrivacy'

export function ChartSection({title, detail, children}: {title: string; detail?: string; children: ReactNode}) {
  return <Section className="pd-activity-panel" padding={5} variant="transparent"><VStack gap={4}>
    <VStack gap={1}><Heading level={3}>{title}</Heading>{detail ? <Text type="supporting" color="secondary">{detail}</Text> : null}</VStack>
    {children}
  </VStack></Section>
}

export function ActivityHighlights({activity, owned = true}: {activity: ProfileActivity; owned?: boolean}) {
  const stats = useMemo(() => analyzeActivity(activity), [activity])
  const metrics = [
    [t('Playtime'), stats.durationCount ? elapsedLabel(stats.seconds) : '—'],
    [t('Matches'), formatNumber(stats.matches.length)],
    [t('Active days'), formatNumber(stats.activeDays)],
    [owned ? t('Daily streak') : t('Games played'), owned ? activity.connectionDays.length ? formatNumber(stats.streak) : '—' : String(stats.gamesPlayed)],
  ]
  return <Grid className="pd-activity-highlights" columns={4} gap={6} width="100%">{metrics.map(([label, value]) => <VStack key={label} gap={1}>
    <Text type="supporting" color="secondary">{label}</Text><Text className="pd-activity-number" weight="semibold" hasTabularNumbers>{value}</Text>
  </VStack>)}</Grid>
}

function Mix({mix, donut = false}: {mix: Record<string, number>; donut?: boolean}) {
  const total = Object.values(mix).reduce((sum, value) => sum + value, 0)
  return <HStack gap={5} align="center" wrap="wrap">
    {donut ? <svg className="pd-activity-donut" viewBox="0 0 100 100" role="img" aria-label={t('Playtime by game')}>
      <circle cx="50" cy="50" r="38" fill="none" stroke="var(--color-background-muted)" strokeWidth="12" />
      {PROFILE_GAMES.map((game, index) => {
        const share = total ? (mix[game] ?? 0) / total * 100 : 0
        const start = total ? PROFILE_GAMES.slice(0, index).reduce((sum, previous) => sum + (mix[previous] ?? 0), 0) / total * 100 : 0
        return <circle key={game} className="pd-chart-draw" cx="50" cy="50" r="38" pathLength="100" fill="none" stroke={GAME_COLORS[game]} strokeWidth="12" strokeDasharray={`${share} ${100 - share}`} strokeDashoffset={-start} transform="rotate(-90 50 50)"><title>{`${game} · ${formatNumber(share, {maximumFractionDigits: 1})}%`}</title></circle>
      })}
    </svg> : <HStack className="pd-activity-mixbar" gap={0} role="img" aria-label={t('Playtime by game')}>
      {PROFILE_GAMES.map(game => <HStack key={game} gap={0} className="pd-activity-mixbar__part" style={{width: `${total ? (mix[game] ?? 0) / total * 100 : 0}%`, background: GAME_COLORS[game]}} />)}
    </HStack>}
    <VStack gap={3}>{PROFILE_GAMES.map(game => <HStack key={game} gap={3} align="center">
      <img className="pd-riot-game-icon" src={gameProfileIcon(game)} alt="" /><VStack gap={0}>
        <Text type="supporting">{game}</Text><Text type="supporting" color="secondary">{elapsedLabel(mix[game] ?? 0)} · {total ? formatNumber((mix[game] ?? 0) / total * 100, {maximumFractionDigits: 1}) : '—'}%</Text>
      </VStack>
    </HStack>)}</VStack>
  </HStack>
}

function WeeklyArea({weeks}: {weeks: Map<string, Record<string, number>>}) {
  const rows = [...weeks].sort(([a], [b]) => a.localeCompare(b)).slice(-26)
  const total = (values: Record<string, number>) => Object.values(values).reduce((a, b) => a + b, 0)
  const max = Math.max(1, ...rows.map(([, values]) => total(values)))
  const x = (i: number) => rows.length > 1 ? i / (rows.length - 1) * 600 : 300
  const y = (value: number) => 150 - value / max * 140
  return <VStack gap={2}><Text type="supporting" color="secondary">{t('Weekly scale')} · {elapsedLabel(max)}</Text>
    <svg className="pd-activity-area" viewBox="0 0 600 160" role="img" aria-label={t('Weekly playtime by game')}>
      {[0, 1, 2, 3].map(line => <line key={line} x1="0" x2="600" y1={line * 45 + 10} y2={line * 45 + 10} stroke="var(--color-border)" />)}
      {PROFILE_GAMES.map((game, index) => {
        const before = (values: Record<string, number>) => PROFILE_GAMES.slice(0, index).reduce((sum, key) => sum + values[key], 0)
        const top = rows.map(([, values], i) => `${x(i)},${y(before(values) + values[game])}`)
        const bottom = rows.map(([, values], i) => `${x(i)},${y(before(values))}`).reverse()
        return <polygon key={game} className="pd-chart-reveal" points={[...top, ...bottom].join(' ')} fill={GAME_COLORS[game]} fillOpacity="0.55"><title>{game}</title></polygon>
      })}
      {rows.map(([week, values], index) => <g key={week} tabIndex={0} role="img" aria-label={`${week} · ${elapsedLabel(total(values))}`}>
        <rect x={Math.max(0, x(index) - 8)} y="0" width="16" height="160" fill="transparent"><title>{`${week} · ${PROFILE_GAMES.map(game => `${game}: ${elapsedLabel(values[game])}`).join(' · ')}`}</title></rect>
      </g>)}
    </svg><HStack justify="between"><Text type="supporting" color="secondary">{rows[0]?.[0] ?? '—'}</Text><Text type="supporting" color="secondary">{rows.at(-1)?.[0] ?? '—'}</Text></HStack>
  </VStack>
}

export function RiotActivity({activity}: {activity: ProfileActivity}) {
  const language = useLocale(), {displayName} = usePlayerPrivacy()
  const stats = useMemo(() => analyzeActivity(activity), [activity])
  const maxHour = Math.max(1, ...stats.hours.flat()), maxSession = Math.max(1, ...stats.histogram)
  const weekdays = Array.from({length: 7}, (_, i) => new Intl.DateTimeFormat(localeTags[language], {weekday: 'short'}).format(new Date(2026, 0, 5 + i)))
  const sessionLabels = ['< 1h', '1–2h', '2–3h', '3–4h', '4–5h', '5–6h', '6h+']
  return <VStack gap={5} className="pd-riot-activity">
    <Grid className="pd-activity-columns" columns={2} gap={5}>
      <ChartSection title={t('Game mix')} detail={t('{{count}} Riot games played', {count: stats.gamesPlayed})}><Mix mix={stats.mix} donut /></ChartSection>
      <ChartSection title={t('Activity over time')} detail={t('Weekly playtime')}><WeeklyArea weeks={stats.weeks} /></ChartSection>
    </Grid>
    <Grid className="pd-activity-columns" columns={2} gap={5}>
      <ChartSection title={t('When you play')} detail={t('Day × hour')}>
        <VStack gap={1}>{stats.hours.map((row, weekday) => <HStack key={weekday} gap={1} align="center" className="pd-play-hours">
          <Text type="supporting" className="pd-play-hours__day">{weekdays[weekday]}</Text>
          {row.map((seconds, hour) => <Tooltip key={hour} content={`${weekdays[weekday]} · ${hour}:00–${hour + 1}:00 · ${elapsedLabel(seconds)}`}><HStack className="pd-play-hours__cell" gap={0} role="img" aria-label={`${weekdays[weekday]} ${hour}:00 · ${elapsedLabel(seconds)}`} style={{'--pd-heat': seconds ? 0.2 + seconds / maxHour * 0.8 : 0} as CSSProperties} /></Tooltip>)}
        </HStack>)}</VStack><HStack justify="between"><Text type="supporting">00h</Text><Text type="supporting">06h</Text><Text type="supporting">12h</Text><Text type="supporting">18h</Text><Text type="supporting">23h</Text></HStack>
      </ChartSection>
      <ChartSection title={t('Play sessions')}>
        <HStack gap={6} wrap="wrap">{[[t('Average session'), stats.average], [t('Longest session'), stats.longest]].map(([label, value]) => <VStack key={label} gap={1}><Text type="supporting" color="secondary">{label}</Text><Text className="pd-activity-number" weight="semibold">{stats.sessions.length ? elapsedLabel(Number(value)) : '—'}</Text></VStack>)}</HStack>
        <svg className="pd-activity-histogram" viewBox="0 0 350 110" role="img" aria-label={t('Session duration distribution')}>{stats.histogram.map((count, i) => <rect className="pd-chart-bar" key={i} x={i * 50 + 5} width="36" y={100 - count / maxSession * 95} height={count / maxSession * 95} fill="var(--color-activity-heat)"><title>{`${sessionLabels[i]} · ${count}`}</title></rect>)}</svg>
        <HStack justify="between">{sessionLabels.map(label => <Text key={label} type="supporting">{label}</Text>)}</HStack>
      </ChartSection>
    </Grid>
    <Grid className="pd-activity-columns" columns={2} gap={5}>
      <ChartSection title={t('Recent balance')}>
        {[7, 30, 90].map(days => <VStack key={days} gap={2}><Text weight="semibold">{t('Last {{count}} days', {count: days})}</Text><Mix mix={recentGameMix(stats.matches, days)} /></VStack>)}
      </ChartSection>
      <VStack gap={5}>
        {/*
        <ChartSection title={t('Game switching')} detail={t('Changes between games within the same session. Rows are the starting game.')}>
          <Table density="compact" aria-label={t('Game switching matrix')} data={PROFILE_GAMES.map((game, index) => ({game, values: stats.switching[index]}))} idKey="game" columns={[
            {key: 'game', header: t('From / to'), width: proportional(2)},
            ...PROFILE_GAMES.map((game, index) => ({key: game, header: <img className="pd-riot-game-icon" src={gameProfileIcon(game)} alt={game} />, width: proportional(1), renderCell: (row: {game: string; values: number[]}) => row.game === game ? '—' : String(row.values[index])})),
          ]} />
        </ChartSection>
        */}
        <ChartSection title={t('Observed Riot IDs')}>
          {activity.identities.length ? <VStack gap={3}>{activity.identities.slice(-8).reverse().map((identity, index) => <HStack key={`${identity.observedAt}-${index}`} gap={3} justify="between" wrap="wrap"><Text weight="semibold">{displayName(identity.riotId)}</Text><Text type="supporting" color="secondary">{new Intl.DateTimeFormat(localeTags[language], {dateStyle: 'medium'}).format(identity.observedAt)}</Text></HStack>)}</VStack> : <Text color="secondary">{t('No identity changes have been observed yet.')}</Text>}
        </ChartSection>
      </VStack>
    </Grid>
  </VStack>
}
