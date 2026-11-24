import type {CSSProperties, ElementType, HTMLAttributes, ReactNode, Ref} from 'react'
import {Flex, Layout as AntLayout} from 'antd'

/** Spacing steps are multiples of 4px, as in the Peaks tokens. */
export type SpacingStep = number
export const space = (step?: SpacingStep) => step === undefined ? undefined : step * 4

const ALIGN = {start: 'flex-start', end: 'flex-end', center: 'center', stretch: 'stretch', baseline: 'baseline'} as const
const JUSTIFY = {start: 'flex-start', end: 'flex-end', center: 'center', between: 'space-between', around: 'space-around', evenly: 'space-evenly'} as const
type Align = keyof typeof ALIGN
type Justify = keyof typeof JUSTIFY
type Size = number | string

interface PaddingProps {
  padding?: SpacingStep
  paddingBlock?: SpacingStep
  paddingBlockStart?: SpacingStep
  paddingBlockEnd?: SpacingStep
  paddingInline?: SpacingStep
  paddingInlineStart?: SpacingStep
}

export function paddingStyle(props: PaddingProps): CSSProperties {
  const style: CSSProperties = {}
  if (props.padding !== undefined) style.padding = space(props.padding)
  if (props.paddingBlock !== undefined) style.paddingBlock = space(props.paddingBlock)
  if (props.paddingInline !== undefined) style.paddingInline = space(props.paddingInline)
  if (props.paddingBlockStart !== undefined) style.paddingBlockStart = space(props.paddingBlockStart)
  if (props.paddingBlockEnd !== undefined) style.paddingBlockEnd = space(props.paddingBlockEnd)
  if (props.paddingInlineStart !== undefined) style.paddingInlineStart = space(props.paddingInlineStart)
  return style
}

export interface StackProps extends PaddingProps, Omit<HTMLAttributes<HTMLElement>, 'wrap'> {
  ref?: Ref<HTMLDivElement>
  as?: ElementType
  gap?: SpacingStep
  align?: Align
  justify?: Justify
  wrap?: boolean | 'wrap' | 'nowrap'
  width?: Size
  height?: Size
  minHeight?: Size
  maxWidth?: Size
  inert?: boolean
  isScrollable?: boolean
  children?: ReactNode
  [data: `data-${string}`]: unknown
}

function Stack({vertical, as, isScrollable, gap, align, justify, wrap, width, height, minHeight, maxWidth, style, padding, paddingBlock, paddingBlockStart, paddingBlockEnd, paddingInline, paddingInlineStart, ...rest}: StackProps & {vertical: boolean}) {
  const Element = (as ?? 'div') as ElementType
  return <Element
    {...rest}
    className={[vertical ? 'pk-vstack' : 'pk-hstack', rest.className].filter(Boolean).join(' ')}
    // Layout goes through custom properties so screen CSS (a grid, say) can still take over.
    style={{
      // Always set, so a stack never inherits its parent's values.
      '--pk-gap': `${space(gap ?? 0)}px`,
      '--pk-align': align ? ALIGN[align] : 'normal', '--pk-justify': justify ? JUSTIFY[justify] : 'normal',
      '--pk-wrap': wrap === true || wrap === 'wrap' ? 'wrap' : 'nowrap',
      width, height, minHeight, maxWidth, overflowY: isScrollable ? 'auto' : undefined,
      ...paddingStyle({padding, paddingBlock, paddingBlockStart, paddingBlockEnd, paddingInline, paddingInlineStart}), ...style,
    } as CSSProperties}
  />
}

export const HStack = (props: StackProps) => <Stack {...props} vertical={false} />
export const VStack = (props: StackProps) => <Stack {...props} vertical />

export function Center({width, height, minHeight, padding, className, children, style, ...rest}: Omit<HTMLAttributes<HTMLDivElement>, 'children'> & {width?: Size; height?: Size; minHeight?: Size; padding?: SpacingStep; children?: ReactNode; [data: `data-${string}`]: unknown}) {
  return <Flex {...rest as object} className={className} align="center" justify="center" style={{width, height, minHeight, padding: space(padding), ...style}}>{children}</Flex>
}

type Columns = number | {minWidth: number; max?: number; repeat?: 'fit' | 'fill'}
const gridColumns = (columns?: Columns) => {
  if (columns === undefined) return undefined
  if (typeof columns === 'number') return `repeat(${columns}, minmax(0, 1fr))`
  const {minWidth, max, repeat = 'fill'} = columns
  // Never more than `max` columns, never narrower than `minWidth`.
  const floor = max ? `max(${minWidth}px, calc((100% - ${(max - 1) * 16}px) / ${max}))` : `${minWidth}px`
  return `repeat(auto-${repeat}, minmax(min(${floor}, 100%), 1fr))`
}

export function Grid({columns, gap, width, maxWidth, justify, className, style, children, ...rest}: Omit<HTMLAttributes<HTMLDivElement>, 'children'> & {columns?: Columns; gap?: SpacingStep; width?: Size; maxWidth?: Size; justify?: Justify; children?: ReactNode}) {
  return <div {...rest} data-columns={typeof columns === 'number' ? columns : undefined} className={['pk-grid', className].filter(Boolean).join(' ')} style={{display: 'grid', gridTemplateColumns: gridColumns(columns), gap: space(gap), width, maxWidth, justifyContent: justify ? JUSTIFY[justify] : undefined, ...style}}>{children}</div>
}

export const GridSpan = ({columns, children}: {columns: number | 'all' | 'full'; children?: ReactNode}) =>
  <div style={{gridColumn: columns === 'all' || columns === 'full' ? '1 / -1' : `span ${columns}`, minWidth: 0}}>{children}</div>

export const AspectRatio = ({ratio, children, className}: {ratio: number; children?: ReactNode; className?: string}) =>
  <div className={className} style={{aspectRatio: ratio, position: 'relative', overflow: 'hidden'}}>{children}</div>

export const VisuallyHidden = ({children, ...rest}: HTMLAttributes<HTMLSpanElement>) =>
  <span {...rest} style={{position: 'absolute', width: 1, height: 1, padding: 0, margin: -1, overflow: 'hidden', clip: 'rect(0 0 0 0)', whiteSpace: 'nowrap', border: 0}}>{children}</span>

/** A region of the page; `muted` sits on a raised surface. */
export function Section({variant = 'transparent', padding, minHeight, className, style, children, dividers, ...rest}: HTMLAttributes<HTMLElement> & {variant?: 'transparent' | 'muted' | 'default'; padding?: SpacingStep; minHeight?: Size; dividers?: boolean | ('top' | 'bottom')[]; [data: `data-${string}`]: unknown}) {
  const raised = variant !== 'transparent'
  return <section {...rest} className={['pk-section', className].filter(Boolean).join(' ')} data-variant={variant}
    data-dividers={Array.isArray(dividers) ? dividers.join(' ') : dividers ? 'top bottom' : undefined}
    style={{padding: space(padding ?? (raised ? 5 : 0)), minHeight, ...style}}>{children}</section>
}

interface LayoutProps {
  contentWidth?: Size
  defaultHasDividers?: boolean
  style?: CSSProperties
  header?: ReactNode
  footer?: ReactNode
  start?: ReactNode
  end?: ReactNode
  content?: ReactNode
  children?: ReactNode
  height?: 'fill' | 'auto' | string
  padding?: SpacingStep
  className?: string
}

/** Header, scrolling content and footer stacked in one column. */
export function Layout({header, footer, start, end, content, children, height = 'fill', padding, className, contentWidth, style}: LayoutProps) {
  return <Flex vertical className={['pk-layout', className].filter(Boolean).join(' ')}
    style={{height: height === 'fill' ? '100%' : height === 'auto' ? undefined : height, minHeight: 0, padding: space(padding), ...style}}>
    {header}
    <Flex style={{flex: 1, minHeight: 0, width: '100%', maxWidth: contentWidth, marginInline: contentWidth ? 'auto' : undefined}}>{start}{content ?? children}{end}</Flex>
    {footer}
  </Flex>
}

export const LayoutHeader = ({children, padding, className}: {children?: ReactNode; padding?: SpacingStep; className?: string; hasDivider?: boolean}) =>
  <header className={['pk-layout__header', className].filter(Boolean).join(' ')} style={{padding: space(padding ?? 4)}}>{children}</header>

export const LayoutFooter = ({children, padding, className}: {children?: ReactNode; padding?: SpacingStep; className?: string; hasDivider?: boolean}) =>
  <footer className={['pk-layout__footer', className].filter(Boolean).join(' ')} style={{padding: space(padding ?? 4)}}>{children}</footer>

export const LayoutContent = ({children, padding, gap, isScrollable = true, className, style, ...rest}: Omit<HTMLAttributes<HTMLDivElement>, 'children'> & {ref?: Ref<HTMLDivElement>; children?: ReactNode; padding?: SpacingStep; gap?: SpacingStep; isScrollable?: boolean}) =>
  <div {...rest} className={['pk-layout__content', className].filter(Boolean).join(' ')} style={{flex: 1, minWidth: 0, minHeight: 0, overflowY: isScrollable ? 'auto' : undefined, padding: space(padding ?? 4), display: gap !== undefined ? 'flex' : undefined, flexDirection: gap !== undefined ? 'column' : undefined, gap: space(gap), ...style}}>{children}</div>

/** The app's top bar: identity on the left, global controls on the right. */
export const TopNav = ({heading, endContent, label, className}: {heading?: ReactNode; endContent?: ReactNode; label?: string; className?: string}) =>
  <AntLayout.Header className={['pk-top-nav', className].filter(Boolean).join(' ')} aria-label={label} role="banner">
    <Flex align="center" justify="space-between" gap={16} style={{height: '100%'}}>{heading}{endContent}</Flex>
  </AntLayout.Header>

export const LayerProvider =({children}: {children?: ReactNode}) => <>{children}</>
