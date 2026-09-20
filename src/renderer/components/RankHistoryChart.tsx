import {HStack} from '@astryxdesign/core/HStack'
import {Text} from '@astryxdesign/core/Text'
import {rankDelta, rankPoints} from '../activityAnalytics'
import {valorantMapName} from '../assets'
import {displayText, formatNumber, localeTags, t, useLocale} from '../i18n'
import type {Game, ProfileActivity} from '../types'
import {ChartSection} from './RiotActivity'

export function RankHistoryChart({game, activity}: {game: Game; activity: ProfileActivity}) {
  const locale = useLocale()
  const matches = activity.matches.filter(match => match.game === game && match.playedAtTimestamp && rankDelta(match.delta) != null).sort((a, b) => a.playedAtTimestamp! - b.playedAtTimestamp!).slice(-30)
  const observations = activity.ranks.filter(rank => rank.game === game && rankPoints(rank) != null).sort((a, b) => a.observedAt - b.observedAt).slice(-30)
  const actualRewards = matches.length > 0
  const unit = game === 'VALORANT' ? 'RR' : 'LP'
  let cumulative = 0
  const rows = actualRewards ? matches.map(match => {
    const delta = rankDelta(match.delta)!
    cumulative += delta
    const map = game === 'VALORANT' && match.map ? valorantMapName(match.map) : match.map
    return {at: match.playedAtTimestamp!, value: cumulative, delta, label: [displayText(map), `${delta > 0 ? '+' : ''}${delta} ${unit}`].filter(Boolean).join(' · ')}
  }) : observations.map((rank, index) => ({at: rank.observedAt, value: rankPoints(rank)!, delta: index ? rankPoints(rank)! - rankPoints(observations[index - 1])! : 0, label: `${displayText(rank.tier)} ${rank.division ?? ''} · ${rank.rating} ${unit}`}))
  const maximumDelta = Math.max(1, ...rows.map(row => Math.abs(row.delta)))
  const min = Math.min(0, ...rows.map(row => row.value)), max = Math.max(1, ...rows.map(row => row.value))
  const x = (i: number) => rows.length > 1 ? 12 + i / (rows.length - 1) * 576 : 300
  const y = (value: number) => 105 - (value - min) / (max - min || 1) * 90
  const gained = rows.reduce((sum, row) => sum + Math.max(0, row.delta), 0), lost = rows.reduce((sum, row) => sum + Math.max(0, -row.delta), 0)
  const date = new Intl.DateTimeFormat(localeTags[locale], {dateStyle: 'medium', timeStyle: 'short'})
  return <ChartSection title={t('Rank progression')} detail={actualRewards ? t('Match gains · {{unit}}', {unit}) : t('Rank snapshots')}>
    {rows.length ? <>
      <HStack gap={6} wrap="wrap"><Text style={{color: 'var(--color-text-green)'}}>+{formatNumber(gained)} {unit} · {t(actualRewards ? 'Gained' : 'Observed increases')}</Text><Text style={{color: 'var(--color-text-red)'}}>−{formatNumber(lost)} {unit} · {t(actualRewards ? 'Lost' : 'Observed decreases')}</Text></HStack>
      <svg className="pd-rank-history" viewBox="0 0 600 200" role="img" aria-label={t('Rank progression')}>
        <line x1="0" x2="600" y1="150" y2="150" stroke="var(--color-border)" />
        <polyline className="pd-chart-line" points={rows.map((row, index) => `${x(index)},${y(row.value)}`).join(' ')} fill="none" stroke="var(--color-accent)" strokeWidth="2" pathLength="1" />
        {rows.map((row, index) => <g key={`${row.at}-${index}`} tabIndex={0} role="img" aria-label={`${date.format(row.at)} · ${row.label}`}>
          <title>{`${date.format(row.at)} · ${row.label}`}</title>
          <rect className="pd-chart-bar" x={x(index) - Math.min(9, 240 / rows.length)} width={Math.min(18, 480 / rows.length)} y={row.delta > 0 ? 150 - row.delta / maximumDelta * 38 : 150} height={Math.abs(row.delta) / maximumDelta * 38} fill={row.delta >= 0 ? 'var(--color-text-green)' : 'var(--color-text-red)'} />
          <circle cx={x(index)} cy={y(row.value)} r="4" fill="var(--color-accent)" />
        </g>)}
      </svg><HStack justify="between"><Text type="supporting" color="secondary">{date.format(rows[0].at)}</Text><Text type="supporting" color="secondary">{date.format(rows.at(-1)!.at)}</Text></HStack>
    </> : <Text color="secondary">{t('No {{unit}} changes yet.', {unit})}</Text>}
  </ChartSection>
}
