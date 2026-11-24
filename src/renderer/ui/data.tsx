import {useCallback, useRef} from 'react'
import type {FocusEvent, KeyboardEvent, ReactNode} from 'react'
import {Table as AntTable} from 'antd'
import type {TableColumnsType} from 'antd'

type Width = {kind: 'pixel'; value: number} | {kind: 'proportional'; value: number}
export const pixel = (value: number): Width => ({kind: 'pixel', value})
export const proportional = (value: number): Width => ({kind: 'proportional', value})

export interface SortDescriptor {sortKey: string; direction: 'ascending' | 'descending'}
export interface TableSortable {sort: SortDescriptor[]; onSortChange: (sort: SortDescriptor[]) => void}
 
export const useTableSortable = <_Row,>(options: TableSortable): TableSortable => options

export interface TableColumn<T> {
  key: string
  header: ReactNode
  width?: Width
  align?: 'start' | 'center' | 'end'
  sortable?: boolean
  renderCell?: (row: T) => ReactNode
}

export function Table<T extends object>({data, columns, idKey, density = 'balanced', className, hasHover, sortable: sortableProp, plugins, dividers: _dividers, ...rest}: {
  plugins?: {sortable?: TableSortable}
  dividers?: 'none' | 'rows' | 'all'
  data: T[]
  columns: TableColumn<T>[]
  idKey: keyof T & string
  density?: 'compact' | 'balanced' | 'spacious'
  hasHover?: boolean
  sortable?: TableSortable
  className?: string
  'aria-label'?: string
}) {
  const sortable = sortableProp ?? plugins?.sortable
  const share = columns.reduce((total, column) => total + (column.width?.kind === 'proportional' ? column.width.value : 0), 0)
  const antColumns: TableColumnsType<T> = columns.map(column => {
    const sorted = sortable?.sort.find(item => item.sortKey === column.key)
    return {
      key: column.key,
      dataIndex: column.key,
      title: column.header,
      align: column.align === 'end' ? 'right' : column.align === 'center' ? 'center' : 'left',
      width: column.width?.kind === 'pixel' ? column.width.value : column.width && share ? `${column.width.value / share * 100}%` : undefined,
      render: column.renderCell ? (_: unknown, row: T) => column.renderCell!(row) : (value: unknown) => value as ReactNode,
      sorter: column.sortable ? true : undefined,
      sortOrder: column.sortable ? sorted ? (sorted.direction === 'ascending' ? 'ascend' : 'descend') : null : undefined,
      sortDirections: column.sortable ? ['ascend', 'descend', 'ascend'] : undefined,
    }
  })
  return <AntTable<T> {...rest} className={['pk-table', className].filter(Boolean).join(' ')} rowKey={idKey}
    columns={antColumns} dataSource={data} pagination={false} size={density === 'compact' ? 'small' : density === 'spacious' ? 'large' : 'middle'}
    rowHoverable={hasHover ?? true} showSorterTooltip={false}
    onChange={(_pagination, _filters, sorter) => {
      const single = Array.isArray(sorter) ? sorter[0] : sorter
      if (!sortable || !single?.columnKey) return
      sortable.onSortChange(single.order ? [{sortKey: String(single.columnKey), direction: single.order === 'ascend' ? 'ascending' : 'descending'}] : [])
    }} />
}

/** Arrow-key movement across a grid of cells, with one tab stop. */
export function useGridFocus<T extends HTMLElement>({columns, cellSelector = '[role="gridcell"]', isCellFocusable = () => true, getFocusTarget, hasRovingTabIndex}: {
  columns: number
  cellSelector?: string
  isCellFocusable?: (cell: HTMLElement) => boolean
  getFocusTarget?: (cell: HTMLElement) => HTMLElement | null
  hasRovingTabIndex?: boolean
  onPageUp?: () => void
  onPageDown?: () => void
}) {
  const gridRef = useRef<T | null>(null)
  const cells = useCallback(() => [...(gridRef.current?.querySelectorAll<HTMLElement>(cellSelector) ?? [])], [cellSelector])
  const focusCell = useCallback((index: number) => {
    const all = cells()
    const cell = all[index]
    if (!cell || !isCellFocusable(cell)) return
    if (hasRovingTabIndex) all.forEach(item => (getFocusTarget?.(item) ?? item).tabIndex = item === cell ? 0 : -1)
    ;(getFocusTarget?.(cell) ?? cell).focus()
  }, [cells, getFocusTarget, hasRovingTabIndex, isCellFocusable])
  const handleKeyDown = useCallback((event: KeyboardEvent) => {
    const all = cells()
    const current = all.findIndex(cell => cell.contains(document.activeElement))
    if (current < 0) return
    const step = {ArrowRight: 1, ArrowLeft: -1, ArrowDown: columns, ArrowUp: -columns}[event.key]
    let next = step === undefined ? undefined : current + step
    if (event.key === 'Home') next = current - current % columns
    if (event.key === 'End') next = current - current % columns + columns - 1
    if (next === undefined) return
    event.preventDefault()
    const direction = Math.sign(next - current) || 1
    while (next >= 0 && next < all.length && !isCellFocusable(all[next])) next += direction
    if (next >= 0 && next < all.length) focusCell(next)
  }, [cells, columns, focusCell, isCellFocusable])
  const handleFocus = useCallback((event: FocusEvent) => {
    if (!hasRovingTabIndex) return
    const all = cells()
    const index = all.findIndex(cell => cell.contains(event.target as Node))
    if (index >= 0) all.forEach((cell, position) => (getFocusTarget?.(cell) ?? cell).tabIndex = position === index ? 0 : -1)
  }, [cells, getFocusTarget, hasRovingTabIndex])
  return {gridRef, handleKeyDown, handleFocus, focusCell, focusFirst: () => focusCell(0), focusLast: () => focusCell(cells().length - 1)}
}
