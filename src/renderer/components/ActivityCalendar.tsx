import {Card} from 'antd'
import {useEffect, useId, useLayoutEffect, useMemo, useRef, useState, type CSSProperties, type RefObject} from 'react'
import {Button, Heading, HStack, Icon, IconButton, Selector, Text, Tooltip, VStack, useGridFocus} from '../ui'
import {analyzeActivity, dayDate, dayKey, GAME_COLORS} from '../activityAnalytics'
import {activityCalendarCells, calendarFocusTarget, isCalendarDayAvailable} from '../activityCalendarKeyboard'
import {shiftTimeline, TIMELINE_HOUR, TIMELINE_HOURS, timelineMarkers, timelineMatchDetails, timelineMatches, timelineStart} from '../activityTimeline'
import {displayText, localeTags, t, useLocale} from '../i18n'
import {gameProfileIcon} from '../profileAssets'
import {PROFILE_GAMES} from '../riotProfile'
import type {Match, ProfileActivity} from '../types'

export function TimelineMarkers({start, now, viewport}: {start: number; now: number; viewport?: RefObject<HTMLDivElement | null>}) {
  const language = useLocale()
  const markers = useMemo(() => timelineMarkers(start, now), [start, now])
  const layer = useRef<HTMLDivElement>(null)
  const date = new Intl.DateTimeFormat(localeTags[language], {dateStyle: 'medium'})
  const clock = new Intl.DateTimeFormat(localeTags[language], {hour: '2-digit', minute: '2-digit'})

  useLayoutEffect(() => {
    const scrollport = viewport?.current, overlay = layer.current
    if (!scrollport || !overlay) return
    const alignLabels = () => {
      const view = scrollport.getBoundingClientRect()
      for (const marker of overlay.querySelectorAll<HTMLElement>('[data-timeline-marker]')) {
        const label = marker.firstElementChild as HTMLElement | null
        const x = marker.getBoundingClientRect().left - view.left
        const halfWidth = (label?.offsetWidth ?? 0) / 2
        marker.dataset.labelVisible = String(x >= 0 && x <= scrollport.clientWidth)
        marker.dataset.labelEdge = x < halfWidth ? 'start' : scrollport.clientWidth - x < halfWidth ? 'end' : 'center'
      }
    }
    alignLabels()
    scrollport.addEventListener('scroll', alignLabels, {passive: true})
    const observer = new ResizeObserver(alignLabels)
    observer.observe(scrollport)
    return () => { scrollport.removeEventListener('scroll', alignLabels); observer.disconnect() }
  }, [viewport, markers, language])

  return <VStack ref={layer} className="pd-day-timeline__markers" gap={0} aria-hidden>
    {markers.map(marker => <VStack key={`${marker.kind}:${marker.timestamp}`} gap={0}
      className={`pd-day-timeline__marker pd-day-timeline__marker--${marker.kind}`} data-timeline-marker={marker.kind}
      data-label-edge={marker.left === 0 ? 'start' : marker.left === 100 ? 'end' : 'center'}
      data-canvas-edge={marker.left === 100 ? 'end' : undefined} style={{left: `${marker.left}%`}}>
      <Text className="pd-day-timeline__marker-label" type="supporting" weight="semibold" hasTabularNumbers>
        <time dateTime={new Date(marker.timestamp).toISOString()}>{marker.kind === 'midnight' ? date.format(marker.timestamp) : clock.format(marker.timestamp)}</time>
      </Text>
    </VStack>)}
  </VStack>
}

export function DayTimeline({date, matches, onSelectMatch, onClose, id, headingRef}: {
  date: string; matches: Match[]; onSelectMatch: (match: Match) => void; onClose: () => void
  id?: string; headingRef?: RefObject<HTMLHeadingElement | null>
}) {
  const language = useLocale()
  const [offsetHours, setOffsetHours] = useState(0)
  const [now, setNow] = useState(() => Date.now())
  const viewport = useRef<HTMLDivElement>(null)
  const pendingScroll = useRef<number | undefined>(undefined)
  const initialized = useRef(false)
  const start = timelineStart(date, offsetHours), end = start + TIMELINE_HOURS * TIMELINE_HOUR
  const entries = useMemo(() => timelineMatches(matches, start), [matches, start])
  const clock = new Intl.DateTimeFormat(localeTags[language], {hour: '2-digit', minute: '2-digit'})
  const dateAndTime = new Intl.DateTimeFormat(localeTags[language], {day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit'})
  const firstMatchTime = entries[0]?.start

  useEffect(() => {
    const updateClock = () => setNow(Date.now())
    const timer = window.setInterval(updateClock, 60_000)
    const onVisibility = () => { if (document.visibilityState === 'visible') updateClock() }
    document.addEventListener('visibilitychange', onVisibility)
    return () => { window.clearInterval(timer); document.removeEventListener('visibilitychange', onVisibility) }
  }, [])

  useLayoutEffect(() => {
    const element = viewport.current
    if (!element) return
    if (pendingScroll.current !== undefined) {
      element.scrollTo({left: pendingScroll.current / TIMELINE_HOURS * element.scrollWidth, behavior: 'instant'})
      pendingScroll.current = undefined
    } else if (!initialized.current && firstMatchTime !== undefined) {
      // Open around the first match instead of forcing a long scroll past an empty morning.
      element.scrollTo({left: Math.max(0, (firstMatchTime - start) / TIMELINE_HOUR - 1) / TIMELINE_HOURS * element.scrollWidth, behavior: 'instant'})
      initialized.current = true
    }
  }, [start, firstMatchTime])

  function shift(direction: -1 | 1) {
    const element = viewport.current
    if (!element || !element.scrollWidth) return
    const next = shiftTimeline(offsetHours, element.scrollLeft / element.scrollWidth * TIMELINE_HOURS,
      element.clientWidth / element.scrollWidth * TIMELINE_HOURS, direction)
    if (next.offsetHours === offsetHours) {
      element.scrollTo({left: next.scrollHours / TIMELINE_HOURS * element.scrollWidth, behavior: 'auto'})
    } else {
      pendingScroll.current = next.scrollHours
      setOffsetHours(next.offsetHours)
    }
  }

  return <VStack id={id} className="pd-day-timeline" gap={3} onKeyDown={event => {
    if (event.key === 'Escape' && !event.defaultPrevented) { event.preventDefault(); onClose() }
  }}>
    <HStack justify="between" align="center" wrap="wrap" gap={3}>
      <VStack gap={0}><Heading ref={headingRef} className="pd-focus-destination" level={4} tabIndex={-1}>{new Intl.DateTimeFormat(localeTags[language], {dateStyle: 'full'}).format(dayDate(date))}</Heading>
        <Text type="supporting" color="secondary" aria-live="polite">{dateAndTime.format(start)} – {dateAndTime.format(end)}</Text></VStack>
      <HStack gap={1}>
        <IconButton size="sm" variant="ghost" icon={<Icon icon="chevronLeft" />} label={t('Previous 6 hours')} tooltip={t('Previous 6 hours')} onClick={() => shift(-1)} />
        <IconButton size="sm" variant="ghost" icon={<Icon icon="chevronRight" />} label={t('Next 6 hours')} tooltip={t('Next 6 hours')} onClick={() => shift(1)} />
        <IconButton size="sm" variant="ghost" icon={<Icon icon="close" />} label={t('Close')} tooltip={t('Close')} onClick={onClose} />
      </HStack>
    </HStack>
    <HStack className="pd-day-timeline__body" gap={3} align="stretch">
      <VStack className="pd-day-timeline__labels" gap={3} aria-hidden>
        <HStack className="pd-day-timeline__axis-spacer" gap={0} />
        {PROFILE_GAMES.map(game => <HStack className="pd-day-timeline__game" key={game} gap={0} align="center" justify="center">
          <Tooltip content={game}><img className="pd-riot-game-icon" src={gameProfileIcon(game)} alt="" /></Tooltip>
        </HStack>)}
      </VStack>
      <VStack ref={viewport} className="pd-day-timeline__viewport" gap={0} isScrollable tabIndex={0} role="region" aria-label={t('Match timeline')}
        onKeyDown={event => {
          if (event.target !== event.currentTarget) return
          if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') { event.preventDefault(); shift(event.key === 'ArrowLeft' ? -1 : 1) }
        }}>
        <VStack className="pd-day-timeline__canvas" gap={3}>
          <HStack className="pd-day-timeline__hours" gap={0} aria-hidden>
            {Array.from({length: TIMELINE_HOURS + 1}, (_, hour) => {
              const time = start + hour * TIMELINE_HOUR
              return <Text className="pd-day-timeline__tick" type="supporting" color="secondary" key={time} style={{left: `${hour / TIMELINE_HOURS * 100}%`}}>
                {clock.format(time)}
              </Text>
            })}
          </HStack>
          {PROFILE_GAMES.map(game => <VStack key={game} className="pd-day-timeline__lane" gap={0} role="group" aria-label={game}>
            {entries.filter(entry => entry.match.game === game).map(entry => {
              const detail = timelineMatchDetails(entry.match).map(displayText).join(' · ')
              const timing = `${clock.format(entry.start)}${entry.end !== undefined ? `–${clock.format(entry.end)}` : ''}`
              const label = [detail, timing, entry.end === undefined ? t('Duration unavailable') : ''].filter(Boolean).join(' · ')
              return <Button className="pd-day-timeline__match" key={`${game}:${entry.match.id}`} label={label} tooltip={label} size="sm" variant="secondary"
                onClick={() => onSelectMatch(entry.match)} style={{left: `${entry.left}%`, width: entry.end === undefined ? 'var(--spacing-8)' : `${entry.width}%`, '--pd-match-color': GAME_COLORS[game]} as CSSProperties}>
                <VStack className="pd-day-timeline__match-copy" gap={0} align="start">
                  {detail ? <Text type="supporting" weight="semibold">{detail}</Text> : null}<Text type="supporting">{timing}</Text>
                </VStack>
              </Button>
            })}
          </VStack>)}
          <TimelineMarkers start={start} now={now} viewport={viewport} />
        </VStack>
      </VStack>
    </HStack>
    {!entries.length ? <Text type="supporting" color="secondary">{t('No matches in this time range.')}</Text> : null}
  </VStack>
}

export function ActivityCalendar({activity, onSelectMatch}: {activity: ProfileActivity; onSelectMatch: (match: Match) => void}) {
  const language = useLocale()
  const {days, matches} = useMemo(() => analyzeActivity(activity), [activity])
  const [selected, setSelected] = useState<string>()
  const [year, setYear] = useState(String(new Date().getFullYear()))
  const [focused, setFocused] = useState(() => dayKey(new Date()))
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const updateClock = () => setNow(Date.now())
    const timer = window.setInterval(updateClock, 60_000)
    const onVisibility = () => { if (document.visibilityState === 'visible') updateClock() }
    document.addEventListener('visibilitychange', onVisibility)
    return () => { window.clearInterval(timer); document.removeEventListener('visibilitychange', onVisibility) }
  }, [])
  const headingRef = useRef<HTMLHeadingElement>(null)
  const focusTimeline = useRef(false)
  const timelineId = useId(), instructionsId = useId()
  const {gridRef, focusCell} = useGridFocus<HTMLDivElement>({
    columns: 7,
    cellSelector: '.pd-activity-calendar__day',
    isCellFocusable: cell => !cell.hasAttribute('disabled'),
    hasRovingTabIndex: true,
  })
  const years = [...new Set([String(new Date().getFullYear()), ...[...days.keys()].map(key => key.slice(0, 4))])].sort().reverse()
  const cells = activityCalendarCells(Number(year))
  const available = cells.filter(date => isCalendarDayAvailable(date, Number(year), now))
  const lastAvailable = available.at(-1)
  const tabStop = available.some(date => dayKey(date) === focused) ? focused : lastAvailable && dayKey(lastAvailable)
  const max = Math.max(1, ...[...days.values()].map(day => day.matches.length))
  const formatter = new Intl.DateTimeFormat(localeTags[language], {dateStyle: 'full'})
  useLayoutEffect(() => {
    if (focusTimeline.current && selected) {
      headingRef.current?.focus()
      focusTimeline.current = false
    }
  }, [selected])
  const closeTimeline = () => {
    setSelected(undefined)
    focusTimeline.current = false
    const index = cells.findIndex(date => dayKey(date) === selected)
    if (index >= 0) focusCell(index)
  }
  return <Card className="pd-activity-panel pd-activity-calendar-panel" size="small" title={t('Activity calendar')}
    extra={<Selector label={t('Year')} isLabelHidden size="sm" value={year} onChange={value => {
        setYear(value); setSelected(undefined); focusTimeline.current = false
        // Keep focus on the year control; the next Tab enters the new year's last available day.
        setFocused('')
      }} options={years.map(value => ({value, label: value}))} />}><VStack gap={3}>
    <Text id={instructionsId} className="pk-visually-hidden">{t('Use arrow keys to move by day or week, Home and End within a week, and Enter to open the timeline.')}</Text>
    <HStack className="pd-activity-calendar__months" gap={1} aria-hidden>{Array.from({length: 12}, (_, month) => <Text key={month} type="supporting" color="secondary" style={{gridColumn: `${Math.floor(cells.findIndex(date => date.getFullYear() === Number(year) && date.getMonth() === month && date.getDate() === 1) / 7) + 1} / span 3`}}>{new Intl.DateTimeFormat(localeTags[language], {month: 'short'}).format(new Date(Number(year), month, 1))}</Text>)}</HStack>
    <HStack ref={gridRef} className="pd-activity-calendar" gap={1} role="group" aria-label={t('Activity calendar')} aria-describedby={instructionsId}>
      {cells.map((date, index) => {
        const key = dayKey(date), count = days.get(key)?.matches.length ?? 0
        const disabled = !isCalendarDayAvailable(date, Number(year), now)
        const label = t('{{count}} matches played · {{date}}', {count, date: formatter.format(date)})
        return <Tooltip key={key} content={label} hasHoverIndication={false}><Button className="pd-activity-calendar__day" label={label} aria-label={label} size="sm" variant="ghost" aria-pressed={selected === key} isDisabled={disabled}
          tabIndex={!disabled && key === tabStop ? 0 : -1} aria-controls={selected === key ? timelineId : undefined} aria-describedby={instructionsId}
          onFocus={() => { setFocused(key); focusCell(index) }}
          onKeyDown={event => {
            if (event.altKey || event.shiftKey) return
            const target = calendarFocusTarget(cells, index, event.key, Number(year), now, event.ctrlKey || event.metaKey)
            if (target !== undefined) { event.preventDefault(); event.stopPropagation(); focusCell(target) }
          }}
          style={{'--pd-heat': count ? 0.24 + 0.76 * Math.sqrt(count / max) : 0} as CSSProperties} onClick={event => {
            setFocused(key)
            if (event.detail === 0) {
              if (selected === key) headingRef.current?.focus()
              else focusTimeline.current = true
            }
            setSelected(key)
          }} />
        </Tooltip>
      })}
    </HStack>
    <HStack justify="end" gap={2} align="center"><Text type="supporting" color="secondary">{t('Less')}</Text>{[0, 0.25, 0.5, 0.75, 1].map(value => <HStack key={value} className="pd-activity-calendar__key" gap={0} style={{'--pd-heat': value} as CSSProperties} />)}<Text type="supporting" color="secondary">{t('More')}</Text></HStack>
    {selected ? <DayTimeline key={selected} id={timelineId} headingRef={headingRef} date={selected} matches={matches} onSelectMatch={onSelectMatch} onClose={closeTimeline} /> : null}
  </VStack></Card>
}
