import {useId, useMemo, useState, type CSSProperties, type ReactNode} from 'react'
import {Card, Col, Flex, Row, Segmented, Statistic, Timeline, Tooltip, Typography} from 'antd'
import {CalendarDays, Clock3, Flame, Gamepad2, History, Hourglass, Timer} from 'lucide-react'
import {analyzeActivity, elapsedLabel, GAME_COLORS, recentGameMix} from '../activityAnalytics'
import {formatNumber, localeTags, t, useLocale} from '../i18n'
import {gameProfileIcon} from '../profileAssets'
import {PROFILE_GAMES} from '../riotProfile'
import type {ProfileActivity} from '../types'
import {useGridFocus} from '../ui'
import {usePlayerPrivacy} from './PlayerPrivacy'

/** A titled panel. The title names it once; `extra` holds a control or a single figure, never a rephrasing. */
export function ChartSection({title, extra, children}: {title: ReactNode; extra?: ReactNode; detail?: string; children: ReactNode}) {
  return <Card className="pd-activity-panel" title={title} extra={extra} size="small" styles={{body: {display: 'flex', flexDirection: 'column', gap: 16}}}>
    {children}
  </Card>
}

const icon = (Glyph: typeof Clock3) => <Glyph size={16} aria-hidden style={{verticalAlign: '-2px'}} />

export function ActivityHighlights({activity, owned = true}: {activity: ProfileActivity; owned?: boolean}) {
  const stats = useMemo(() => analyzeActivity(activity), [activity])
  const metrics: [string, string, ReactNode][] = [
    [t('Playtime'), stats.durationCount ? elapsedLabel(stats.seconds) : '—', icon(Clock3)],
    [t('Matches'), formatNumber(stats.matches.length), icon(Gamepad2)],
    [t('Active days'), formatNumber(stats.activeDays), icon(CalendarDays)],
    owned ? [t('Daily streak'), activity.connectionDays.length ? formatNumber(stats.streak) : '—', icon(Flame)]
      : [t('Games played'), String(stats.gamesPlayed), icon(Gamepad2)],
  ]
  return <Card size="small" className="pd-activity-highlights">
    <Row gutter={[24, 16]}>{metrics.map(([label, value, prefix]) => <Col key={label} xs={12} md={6}>
      <Statistic title={label} value={value} prefix={prefix} />
    </Col>)}</Row>
  </Card>
}

function Donut({mix}: {mix: Record<string, number>}) {
  const total = Object.values(mix).reduce((sum, value) => sum + value, 0)
  return <svg className="pd-activity-donut" viewBox="0 0 100 100" role="img" aria-label={t('Playtime by game')}>
    <circle cx="50" cy="50" r="38" fill="none" stroke="var(--color-background-muted)" strokeWidth="12" />
    {PROFILE_GAMES.map((game, index) => {
      const share = total ? (mix[game] ?? 0) / total * 100 : 0
      const start = total ? PROFILE_GAMES.slice(0, index).reduce((sum, previous) => sum + (mix[previous] ?? 0), 0) / total * 100 : 0
      return <circle key={game} className="pd-chart-draw" cx="50" cy="50" r="38" pathLength="100" fill="none" stroke={GAME_COLORS[game]} strokeWidth="12" strokeDasharray={`${share} ${100 - share}`} strokeDashoffset={-start} transform="rotate(-90 50 50)"><title>{`${game} · ${formatNumber(share, {maximumFractionDigits: 1})}%`}</title></circle>
    })}
  </svg>
}

/** One breakdown with a period switch, instead of the same list repeated per period. */
function GameMix({activity}: {activity: ReturnType<typeof analyzeActivity>}) {
  const [period, setPeriod] = useState<'all' | '7' | '30' | '90'>('all')
  const mix = period === 'all' ? activity.mix : recentGameMix(activity.matches, Number(period))
  const total = Object.values(mix).reduce((sum, value) => sum + value, 0)
  return <ChartSection title={t('Game mix')} extra={<Segmented size="small" value={period} onChange={value => setPeriod(value as typeof period)}
    options={[{value: '7', label: t('{{count}} d', {count: 7})}, {value: '30', label: t('{{count}} d', {count: 30})}, {value: '90', label: t('{{count}} d', {count: 90})}, {value: 'all', label: t('All')}]} />}>
    <Flex gap={24} align="center" wrap>
      <Donut mix={mix} />
      <Flex vertical gap={12} style={{flex: 1, minWidth: 160}}>
        {PROFILE_GAMES.map(game => {
          const share = total ? (mix[game] ?? 0) / total * 100 : 0
          return <Flex key={game} gap={12} align="center">
            <Tooltip title={game}><img className="pd-riot-game-icon" src={gameProfileIcon(game)} alt={game} /></Tooltip>
            <div className="pd-mix-bar" aria-hidden><span style={{width: `${share}%`, background: GAME_COLORS[game]}} /></div>
            <Typography.Text type="secondary" className="pd-mix-value">{elapsedLabel(mix[game] ?? 0)} · {total ? formatNumber(share, {maximumFractionDigits: 0}) : '—'}%</Typography.Text>
          </Flex>
        })}
      </Flex>
    </Flex>
  </ChartSection>
}

function WeeklyArea({weeks}: {weeks: Map<string, Record<string, number>>}) {
  const rows = [...weeks].sort(([a], [b]) => a.localeCompare(b)).slice(-26)
  const total = (values: Record<string, number>) => Object.values(values).reduce((a, b) => a + b, 0)
  const max = Math.max(1, ...rows.map(([, values]) => total(values)))
  const x = (i: number) => rows.length > 1 ? i / (rows.length - 1) * 600 : 300
  const y = (value: number) => 150 - value / max * 140
  return <ChartSection title={t('Activity over time')} extra={<Tooltip title={t('Weekly scale')}><Typography.Text type="secondary">{icon(Hourglass)} {elapsedLabel(max)}</Typography.Text></Tooltip>}>
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
    </svg>
    <Flex justify="space-between"><Typography.Text type="secondary">{rows[0]?.[0] ?? '—'}</Typography.Text><Typography.Text type="secondary">{rows.at(-1)?.[0] ?? '—'}</Typography.Text></Flex>
  </ChartSection>
}

export function RiotActivity({activity}: {activity: ProfileActivity}) {
  const language = useLocale(), {displayName} = usePlayerPrivacy()
  const hoursHintId = useId(), sessionDescriptionId = useId()
  const {gridRef, handleKeyDown, handleFocus, focusCell} = useGridFocus<HTMLDivElement>({
    columns: 24, cellSelector: '[role="gridcell"]', hasRovingTabIndex: true,
  })
  const stats = useMemo(() => analyzeActivity(activity), [activity])
  const maxHour = Math.max(1, ...stats.hours.flat()), maxSession = Math.max(1, ...stats.histogram)
  const weekdays = Array.from({length: 7}, (_, i) => new Intl.DateTimeFormat(localeTags[language], {weekday: 'short'}).format(new Date(2026, 0, 5 + i)))
  const sessionLabels = ['< 1h', '1–2h', '2–3h', '3–4h', '4–5h', '5–6h', '6h+']
  const sessionDescription = stats.histogram.map((count, i) => `${sessionLabels[i]} · ${t('Sessions: {{count}}', {count})}`).join('; ')
  const identities = activity.identities.slice(-8).reverse()
  return <Row gutter={[16, 16]} className="pd-riot-activity">
    <Col xs={24} lg={12}><GameMix activity={stats} /></Col>
    <Col xs={24} lg={12}><WeeklyArea weeks={stats.weeks} /></Col>
    <Col xs={24} lg={12}>
      <ChartSection title={t('When you play')}>
        <div ref={gridRef} className="pd-play-hours-grid" role="grid" aria-label={t('When you play')} aria-describedby={hoursHintId} aria-readonly
          onKeyDown={handleKeyDown} onFocus={handleFocus}>
          {stats.hours.map((row, weekday) => <div key={weekday} className="pd-play-hours" role="row">
            <Typography.Text type="secondary" className="pd-play-hours__day" aria-hidden>{weekdays[weekday]}</Typography.Text>
            {row.map((seconds, hour) => {
              const label = `${weekdays[weekday]} · ${hour}:00–${hour + 1}:00 · ${elapsedLabel(seconds)}`
              return <Tooltip key={hour} title={label} mouseEnterDelay={0}>
                <span className="pd-play-hours__cell" role="gridcell" aria-label={label}
                  tabIndex={weekday === 0 && hour === 0 ? 0 : -1} onFocus={() => focusCell(weekday * 24 + hour)}
                  style={{'--pd-heat': seconds ? 0.2 + seconds / maxHour * 0.8 : 0} as CSSProperties} />
              </Tooltip>
            })}
          </div>)}
        </div>
        <Flex justify="space-between" aria-hidden className="pd-play-hours__scale">{['00h', '06h', '12h', '18h', '23h'].map(hour => <Typography.Text key={hour} type="secondary">{hour}</Typography.Text>)}</Flex>
        <span id={hoursHintId} className="pk-visually-hidden">{t('Use arrow keys to explore hours. Home and End move within a day.')}</span>
      </ChartSection>
    </Col>
    <Col xs={24} lg={12}>
      <ChartSection title={t('Play sessions')}>
        <Row gutter={24}>
          <Col span={12}><Statistic title={t('Average session')} value={stats.sessions.length ? elapsedLabel(stats.average) : '—'} prefix={icon(Timer)} /></Col>
          <Col span={12}><Statistic title={t('Longest session')} value={stats.sessions.length ? elapsedLabel(stats.longest) : '—'} prefix={icon(Hourglass)} /></Col>
        </Row>
        <svg className="pd-activity-histogram" viewBox="0 0 350 110" role="img" aria-label={t('Session duration distribution')} aria-describedby={sessionDescriptionId}>
          <desc id={sessionDescriptionId}>{sessionDescription}</desc>
          {stats.histogram.map((count, i) => <rect className="pd-chart-bar" key={i} x={i * 50 + 5} width="36" y={100 - count / maxSession * 95} height={count / maxSession * 95} fill="var(--color-activity-heat)"><title>{`${sessionLabels[i]} · ${formatNumber(count)}`}</title></rect>)}
        </svg>
        <div className="pd-histogram-labels" aria-hidden>{sessionLabels.map(label => <Typography.Text key={label} type="secondary">{label}</Typography.Text>)}</div>
      </ChartSection>
    </Col>
    {identities.length > 1 ? <Col xs={24} lg={12}>
      <ChartSection title={<Flex gap={8} align="center">{icon(History)}{t('Observed Riot IDs')}</Flex>}>
        <Timeline items={identities.map(identity => ({
          children: <Flex justify="space-between" gap={12} wrap><Typography.Text strong>{displayName(identity.riotId)}</Typography.Text>
            <Typography.Text type="secondary">{new Intl.DateTimeFormat(localeTags[language], {dateStyle: 'medium'}).format(identity.observedAt)}</Typography.Text></Flex>,
        }))} />
      </ChartSection>
    </Col> : null}
  </Row>
}
