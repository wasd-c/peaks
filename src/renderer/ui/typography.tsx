import type {ComponentType, CSSProperties, ElementType, HTMLAttributes, ReactNode, Ref} from 'react'
import {Typography} from 'antd'
import {Check, ChevronDown, ChevronLeft, ChevronRight, ChevronUp, X} from 'lucide-react'

type TextType = 'body' | 'supporting' | 'large' | 'label' | 'code' | 'inherit' | 'display-1' | 'display-2' | 'display-3'
type TextColor = 'primary' | 'secondary' | 'inherit' | 'disabled' | 'accent' | 'error' | 'success' | 'warning'
type Weight = 'normal' | 'medium' | 'semibold' | 'bold'

const WEIGHT: Record<Weight, number> = {normal: 400, medium: 500, semibold: 600, bold: 700}
const COLOR: Record<TextColor, string | undefined> = {
  primary: 'var(--color-text-primary)', secondary: 'var(--color-text-secondary)', inherit: 'inherit',
  disabled: 'var(--color-text-disabled)', accent: 'var(--color-text-accent)', error: 'var(--color-error)',
  success: 'var(--color-success)', warning: 'var(--color-warning)',
}

export function typeStyle(type: TextType | undefined): CSSProperties {
  switch (type) {
    case 'supporting': return {fontSize: 'var(--text-supporting-size)', lineHeight: 'var(--text-supporting-leading)'}
    case 'large': return {fontSize: 'var(--text-large-size)', lineHeight: 'var(--text-large-leading)', fontWeight: 600}
    case 'label': return {fontSize: 'var(--text-label-size)', lineHeight: 'var(--text-label-leading)', fontWeight: 500}
    case 'code': return {fontFamily: 'var(--font-family-code)', fontSize: 'var(--text-code-size)'}
    case 'inherit': return {fontSize: 'inherit', lineHeight: 'inherit'}
    case 'display-1': case 'display-2': case 'display-3':
      return {fontFamily: 'var(--font-family-heading)', fontSize: `var(--text-${type}-size)`, lineHeight: `var(--text-${type}-leading)`, letterSpacing: 'var(--peaks-tracking-heading)'}
    default: return {fontSize: 'var(--text-body-size)', lineHeight: 'var(--text-body-leading)'}
  }
}

const clamp = (lines?: number): CSSProperties => lines ? {display: '-webkit-box', WebkitLineClamp: lines, WebkitBoxOrient: 'vertical', overflow: 'hidden'} : {}

export interface TextProps extends Omit<HTMLAttributes<HTMLElement>, 'color'> {
  ref?: Ref<HTMLElement>
  as?: ElementType
  type?: TextType
  color?: TextColor
  weight?: Weight
  justify?: 'start' | 'center' | 'end'
  maxLines?: number
  textWrap?: 'balance' | 'pretty' | 'wrap' | 'nowrap'
  size?: string
  display?: 'block' | 'inline' | 'inline-block'
  hasTabularNumbers?: boolean
  children?: ReactNode
  [data: `data-${string}`]: unknown
}

export function Text({as, type, color, weight, justify, maxLines, textWrap, size: _size, display, hasTabularNumbers, style, className, ...rest}: TextProps) {
  const Component = (as ?? 'span') as ElementType
  return <Component {...rest}
    className={['ant-typography pk-text', className].filter(Boolean).join(' ')}
    style={{
      color: color ? COLOR[color] : undefined, fontWeight: weight ? WEIGHT[weight] : undefined,
      textAlign: justify, textWrap, display: maxLines ? undefined : display ?? (justify ? 'block' : undefined),
      fontVariantNumeric: hasTabularNumbers ? 'tabular-nums' : undefined,
      ...typeStyle(type), ...clamp(maxLines), ...style,
    }} />
}

export function Heading({level = 2, type, justify, textWrap, className, style, children, ...rest}: Omit<HTMLAttributes<HTMLHeadingElement>, 'color'> & {
  ref?: Ref<HTMLHeadingElement>
  level?: 1 | 2 | 3 | 4 | 5 | 6
  type?: 'display-1' | 'display-2' | 'display-3'
  justify?: 'start' | 'center' | 'end'
  textWrap?: 'balance' | 'pretty' | 'wrap'
  children?: ReactNode
}) {
  return <Typography.Title {...rest as object} level={Math.min(level, 5) as 1 | 2 | 3 | 4 | 5}
    className={['pk-heading', className].filter(Boolean).join(' ')}
    style={{margin: 0, textAlign: justify, textWrap, fontFamily: 'var(--font-family-heading)', letterSpacing: 'var(--peaks-tracking-heading)', ...(type ? typeStyle(type) : {}), ...(type ? {fontWeight: 700} : {}), ...style}}>
    {children}
  </Typography.Title>
}

type IconType = ComponentType<{size?: number | string; className?: string; color?: string; strokeWidth?: number; 'aria-hidden'?: boolean}>
const ICON_SIZE = {xsm: 12, sm: 14, md: 16, lg: 20, xl: 24} as const

const NAMED: Record<string, IconType> = {chevronLeft: ChevronLeft, chevronRight: ChevronRight, close: X, chevronDown: ChevronDown, chevronUp: ChevronUp, check: Check}

export function Icon({icon, size = 'md', color, label, className}: {
  icon: IconType | keyof typeof NAMED
  size?: keyof typeof ICON_SIZE | number
  color?: TextColor
  label?: string
  className?: string
}) {
  const pixels = typeof size === 'number' ? size : ICON_SIZE[size]
  const Glyph = typeof icon === 'string' ? NAMED[icon] : icon
  const glyph = <Glyph size={pixels} className={['pk-icon', className].filter(Boolean).join(' ')} color={color ? COLOR[color] : 'currentColor'} aria-hidden />
  return label ? <span role="img" aria-label={label} style={{display: 'inline-flex'}}>{glyph}</span> : glyph
}

export type {IconType}
