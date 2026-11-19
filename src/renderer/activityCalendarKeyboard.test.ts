import {describe, expect, it} from 'vitest'
import {dayKey} from './activityAnalytics'
import {activityCalendarCells, calendarFocusTarget, isCalendarDayAvailable} from './activityCalendarKeyboard'

const navigate = (date: string, key: string, wholeYear = false, today = '2026-09-21') => {
  const year = Number(date.slice(0, 4)), cells = activityCalendarCells(year)
  const current = cells.findIndex(cell => dayKey(cell) === date)
  const index = calendarFocusTarget(cells, current, key, year, new Date(`${today}T12:00:00`).getTime(), wholeYear)
  return index === undefined ? undefined : dayKey(cells[index])
}

describe('activity calendar keyboard geometry', () => {
  it('moves vertically by day and horizontally by week', () => {
    expect(navigate('2026-09-10', 'ArrowUp')).toBe('2026-09-09')
    expect(navigate('2026-09-10', 'ArrowDown')).toBe('2026-09-11')
    expect(navigate('2026-09-10', 'ArrowLeft')).toBe('2026-09-03')
    expect(navigate('2026-09-10', 'ArrowRight')).toBe('2026-09-17')
  })
  it('crosses a week boundary chronologically without jumping a week', () => {
    expect(navigate('2026-09-13', 'ArrowDown')).toBe('2026-09-14')
    expect(navigate('2026-09-14', 'ArrowUp')).toBe('2026-09-13')
  })
  it('keeps year padding and future dates out of keyboard navigation', () => {
    expect(navigate('2026-01-01', 'ArrowUp')).toBe('2026-01-01')
    expect(navigate('2026-01-05', 'ArrowLeft')).toBe('2026-01-05')
    expect(navigate('2026-09-21', 'ArrowDown')).toBe('2026-09-21')
    expect(navigate('2026-09-17', 'ArrowRight')).toBe('2026-09-17')
  })
  it('uses the available start and end of a partial week', () => {
    expect(navigate('2026-01-03', 'Home')).toBe('2026-01-01')
    expect(navigate('2026-01-03', 'End')).toBe('2026-01-04')
    expect(navigate('2026-09-21', 'End')).toBe('2026-09-21')
  })
  it('uses the first and last available days for modified Home/End', () => {
    expect(navigate('2026-07-08', 'Home', true)).toBe('2026-01-01')
    expect(navigate('2026-07-08', 'End', true)).toBe('2026-09-21')
    expect(navigate('2025-07-08', 'End', true)).toBe('2025-12-31')
  })
  it('includes leap day and moves through it as a single calendar day', () => {
    expect(navigate('2024-02-28', 'ArrowDown')).toBe('2024-02-29')
    expect(navigate('2024-02-29', 'ArrowDown')).toBe('2024-03-01')
    const now = new Date('2026-09-21T12:00:00').getTime()
    expect(activityCalendarCells(2024).filter(date => isCalendarDayAvailable(date, 2024, now))).toHaveLength(366)
  })
  it('leaves Tab, Enter, and Space to native button behavior', () => {
    for (const key of ['Tab', 'Enter', ' ']) expect(navigate('2026-09-10', key)).toBeUndefined()
  })
})
