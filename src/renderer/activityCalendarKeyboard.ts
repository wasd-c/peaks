import {nextDay} from './activityAnalytics'

export function activityCalendarCells(year: number) {
  const january = new Date(year, 0, 1)
  const first = nextDay(january, -((january.getDay() + 6) % 7))
  return Array.from({length: 371}, (_, index) => nextDay(first, index))
    .filter(date => date < new Date(year + 1, 0, 8))
}

export function isCalendarDayAvailable(date: Date, year: number, now: number) {
  return date.getFullYear() === year && date.getTime() <= now
}

/** Dates run down each Monday–Sunday column, then continue in the next week. */
export function calendarFocusTarget(cells: Date[], current: number, key: string, year: number, now: number, wholeYear = false): number | undefined {
  const available = (index: number) => isCalendarDayAvailable(cells[index], year, now)
  const steps: Record<string, number> = {ArrowUp: -1, ArrowDown: 1, ArrowLeft: -7, ArrowRight: 7}
  if (key in steps) {
    const step = steps[key]
    for (let index = current + step; index >= 0 && index < cells.length; index += step) {
      if (available(index)) return index
    }
    return current
  }
  if (key !== 'Home' && key !== 'End') return undefined
  const weekStart = Math.floor(current / 7) * 7
  const first = wholeYear ? 0 : weekStart
  const last = wholeYear ? cells.length - 1 : Math.min(weekStart + 6, cells.length - 1)
  const step = key === 'Home' ? 1 : -1
  for (let index = key === 'Home' ? first : last; index >= first && index <= last; index += step) {
    if (available(index)) return index
  }
  return current
}
