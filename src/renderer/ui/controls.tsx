import {Children, isValidElement, useId, useState} from 'react'
import type {ChangeEvent, CSSProperties, HTMLAttributes, KeyboardEvent, MouseEvent, ReactElement, ReactNode, Ref} from 'react'
import {Avatar as AntAvatar, Badge, Button as AntButton, Card as AntCard, Collapse, Divider as AntDivider, Empty, Flex, Input, Progress, Segmented, Select, Skeleton as AntSkeleton, Space, Spin, Switch as AntSwitch, Tabs, Tag, Tooltip as AntTooltip, Upload} from 'antd'
import type {InputRef} from 'antd'
import {space, type SpacingStep} from './layout'
import {Icon, Text, type IconType} from './typography'

const isIconType = (value: unknown): value is IconType =>
  typeof value === 'function' || (typeof value === 'object' && value !== null && 'render' in value)

const cx = (...names: (string | false | undefined)[]) => names.filter(Boolean).join(' ')

/* ---------- Buttons ---------- */

export type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'destructive' | 'tertiary'
type ButtonSize = 'sm' | 'md' | 'lg'
const BUTTON_SIZE = {sm: 'small', md: 'middle', lg: 'large'} as const

function buttonType(variant: ButtonVariant = 'secondary') {
  if (variant === 'primary') return {type: 'primary' as const}
  if (variant === 'destructive') return {type: 'primary' as const, danger: true}
  if (variant === 'ghost') return {type: 'text' as const}
  if (variant === 'tertiary') return {type: 'link' as const}
  return {type: 'default' as const}
}

export interface ButtonProps extends Omit<HTMLAttributes<HTMLButtonElement>, 'onClick'> {
  ref?: Ref<HTMLButtonElement>
  label: string
  icon?: ReactNode
  endContent?: ReactNode
  variant?: ButtonVariant
  size?: ButtonSize
  isIconOnly?: boolean
  isDisabled?: boolean
  isLoading?: boolean
  width?: string | number
  tooltip?: ReactNode
  onClick?: (event: MouseEvent<HTMLElement>) => void
  clickAction?: () => unknown
  isInterruptible?: boolean
  href?: string
  target?: string
  rel?: string
  type?: 'button' | 'submit'
  src?: string
  alt?: string
  children?: ReactNode
  [data: `data-${string}`]: unknown
}

export function Button({label, icon, endContent, variant, size = 'md', isIconOnly, isDisabled, isLoading, width, tooltip, onClick, clickAction, isInterruptible: _isInterruptible, type = 'button', src, alt, children, className, style, ...rest}: ButtonProps) {
  const [pending, setPending] = useState(false)
  const handleClick = (event: MouseEvent<HTMLElement>) => {
    onClick?.(event)
    const result = clickAction?.()
    if (result instanceof Promise) {
      setPending(true)
      void result.finally(() => setPending(false))
    }
  }
  const glyph = src ? <img src={src} alt={alt ?? ''} className="pk-button__image" /> : icon
  const button = <AntButton {...rest as object} {...buttonType(variant)} htmlType={type} size={BUTTON_SIZE[size]}
    className={cx('pk-button', className)} style={{width, ...style}}
    icon={glyph} iconPlacement="start" loading={isLoading || pending} disabled={isDisabled}
    aria-label={isIconOnly || children ? label : undefined} onClick={handleClick as never}>
    {isIconOnly ? null : children ?? <>{label}{endContent}</>}
  </AntButton>
  const hint = tooltip ?? (isIconOnly ? label : undefined)
  return hint ? <AntTooltip title={hint}>{button}</AntTooltip> : button
}

export const IconButton = ({icon, label, ...rest}: Omit<ButtonProps, 'isIconOnly'>) => <Button {...rest} icon={icon} label={label} isIconOnly />

export const ButtonGroup = ({label, children}: {label?: string; size?: ButtonSize; children?: ReactNode}) =>
  <Space.Compact aria-label={label}>{children}</Space.Compact>

/* ---------- Identity ---------- */

const AVATAR_SIZE = {xsm: 20, sm: 24, md: 36, lg: 48, xl: 128} as const
const initials = (name?: string) => (name ?? '').replace(/#.*/, '').split(/\s+/).filter(Boolean).slice(0, 2).map(part => part[0]?.toUpperCase()).join('')

type DotVariant = 'success' | 'neutral' | 'error' | 'warning' | 'accent'
const DOT_STATUS = {success: 'success', neutral: 'default', error: 'error', warning: 'warning', accent: 'processing'} as const

export const AvatarStatusDot = ({variant = 'success', label}: {variant?: 'success' | 'neutral' | 'error'; label?: string}) =>
  <Badge status={DOT_STATUS[variant]} aria-label={label} className="pk-avatar__status" />

export function Avatar({src, name, alt, size = 'md', shape = 'circle', tooltip = true, status, className, onClick}: {
  src?: string
  name?: string
  alt?: string
  size?: keyof typeof AVATAR_SIZE | number
  shape?: 'circle' | 'rounded' | 'square'
  tooltip?: string | boolean
  status?: ReactNode
  className?: string
  onClick?: (event: MouseEvent) => void
}) {
  const pixels = typeof size === 'number' ? size : AVATAR_SIZE[size]
  const avatar = <AntAvatar src={src} alt={alt ?? name} size={pixels} shape={shape === 'circle' ? 'circle' : 'square'}
    className={cx('pk-avatar', className)} style={shape === 'square' ? {borderRadius: 0} : undefined}
    onClick={onClick as never}>{initials(name)}</AntAvatar>
  const withStatus = status ? <span className="pk-avatar-wrap">{avatar}{status}</span> : avatar
  const title = tooltip === true ? name : tooltip || undefined
  return title ? <AntTooltip title={title}>{withStatus}</AntTooltip> : withStatus
}

export function Thumbnail({src, alt, label, className}: {src?: string; alt?: string; label?: string; className?: string}) {
  return <span className={cx('pk-thumbnail', className)} title={label}><img src={src} alt={alt ?? label ?? ''} /></span>
}

/* ---------- Status ---------- */

type TokenColor = 'default' | 'red' | 'orange' | 'yellow' | 'green' | 'teal' | 'cyan' | 'blue' | 'purple' | 'pink' | 'gray' | 'accent'
const TAG_COLOR: Partial<Record<TokenColor, string>> = {red: 'error', orange: 'orange', yellow: 'gold', green: 'success', teal: 'cyan', cyan: 'cyan', blue: 'blue', purple: 'purple', pink: 'magenta'}

export function Token({label, color = 'default', icon, description, onClick, className}: {
  label: ReactNode
  color?: TokenColor
  size?: 'sm' | 'md'
  icon?: ReactNode
  description?: string
  onClick?: () => void
  className?: string
}) {
  const tag = <Tag color={TAG_COLOR[color]} icon={icon} className={cx('pk-token', className)}>{label}</Tag>
  if (!onClick) return description ? <AntTooltip title={description}>{tag}</AntTooltip> : tag
  return <button type="button" className="pk-token-button" onClick={onClick} aria-description={description}>{tag}</button>
}

export const StatusDot = ({variant = 'neutral', label, isPulsing}: {variant?: DotVariant; label: string; isPulsing?: boolean}) =>
  <Badge status={isPulsing ? 'processing' : DOT_STATUS[variant]} aria-label={label} title={label} className="pk-status-dot" />

const SPIN_SIZE = {sm: 'small', md: 'medium', lg: 'large', xl: 'large'} as const
export const Spinner = ({size = 'md', label, ...rest}: {size?: keyof typeof SPIN_SIZE; label?: string; 'aria-label'?: string}) =>
  <Spin size={SPIN_SIZE[size]} aria-label={label ?? rest['aria-label']} />

export function ProgressBar({value = 0, max = 100, label, isLabelHidden = true, hasValueLabel, isIndeterminate, variant = 'accent', className}: {
  value?: number
  isIndeterminate?: boolean
  max?: number
  label: string
  isLabelHidden?: boolean
  hasValueLabel?: boolean
  variant?: 'accent' | 'neutral' | 'success' | 'warning' | 'error'
  className?: string
}) {
  const percent = max > 0 ? Math.max(0, Math.min(100, value / max * 100)) : 0
  const stroke = variant === 'neutral' ? 'var(--color-text-secondary)' : variant === 'accent' ? undefined : `var(--color-${variant})`
  if (isIndeterminate) return <Flex vertical gap={8} align="center" className={cx('pk-progress', className)}><Spin aria-label={label} />{isLabelHidden ? null : <Text type="supporting" color="secondary">{label}</Text>}</Flex>
  return <Flex vertical gap={4} className={cx('pk-progress', className)}>
    {isLabelHidden ? null : <Text type="supporting" color="secondary">{label}</Text>}
    <Progress percent={percent} showInfo={Boolean(hasValueLabel)} strokeColor={stroke} size="small" aria-label={label}
      format={() => `${Math.round(percent)} %`} />
  </Flex>
}

export const Skeleton = ({width, height, radius, className}: {width?: string | number; height?: string | number; radius?: string | number; index?: number; className?: string}) =>
  <AntSkeleton.Node active className={className} style={{width, height, borderRadius: radius}}><span /></AntSkeleton.Node>

export function EmptyState({icon, title, description, actions, color: _color, children}: {icon?: ReactNode; title?: ReactNode; description?: ReactNode; actions?: ReactNode; color?: string; children?: ReactNode}) {
  return <Empty className="pk-empty" image={icon ? <span className="pk-empty__icon">{icon}</span> : Empty.PRESENTED_IMAGE_SIMPLE}
    description={<Flex vertical gap={4} align="center">
      {title ? <Text weight="semibold" color="primary">{title}</Text> : null}
      {description ? <Text type="supporting" color="secondary">{description}</Text> : null}
    </Flex>}>{actions}{children}</Empty>
}

/* ---------- Surfaces ---------- */

export function Card({padding, variant, className, children, style, ...rest}: HTMLAttributes<HTMLDivElement> & {padding?: SpacingStep; variant?: 'default' | 'muted' | 'outlined'}) {
  return <AntCard {...rest as object} variant={variant === 'muted' ? 'borderless' : 'outlined'} className={cx('pk-card', className)}
    styles={{body: {padding: space(padding ?? 5)}}} style={style}>{children}</AntCard>
}

export const Divider = ({orientation = 'horizontal', variant: _variant, style, ...rest}: {orientation?: 'horizontal' | 'vertical'; variant?: string; style?: CSSProperties; 'aria-hidden'?: boolean | 'true'}) =>
  <AntDivider {...rest} orientation={orientation} style={{margin: 0, ...style}} />

export const Collapsible = ({trigger, defaultIsOpen, children}: {trigger: ReactNode; defaultIsOpen?: boolean; weight?: string; children?: ReactNode}) =>
  <Collapse ghost defaultActiveKey={defaultIsOpen ? ['panel'] : []} items={[{key: 'panel', label: trigger, children}]} />

export const FormLayout = ({children}: {children?: ReactNode}) => <Flex vertical gap={16} className="pk-form">{children}</Flex>

/* ---------- Fields ---------- */

function Field({id, label, isLabelHidden, description, isOptional, children}: {id: string; label: string; isLabelHidden?: boolean; description?: string; isOptional?: boolean; children: ReactNode}) {
  return <div className="pk-field">
    <label className={isLabelHidden ? 'pk-visually-hidden' : 'pk-field__label'} htmlFor={id}>{label}</label>
    {children}
    {description ? <Text type="supporting" color="secondary">{description}</Text> : null}
    {isOptional ? null : null}
  </div>
}

export interface TextInputProps {
  ref?: Ref<InputRef>
  label: string
  isLabelHidden?: boolean
  description?: string
  isOptional?: boolean
  isDisabled?: boolean
  type?: 'text' | 'password' | 'search' | 'email' | 'number'
  value: string
  onChange?: (value: string, event: ChangeEvent<HTMLInputElement>) => void
  placeholder?: string
  startIcon?: ReactNode | IconType
  hasClear?: boolean
  hasAutoFocus?: boolean
  onEnter?: () => void
  onKeyDown?: (event: KeyboardEvent<HTMLInputElement>) => void
  autoComplete?: string
  size?: 'sm' | 'md' | 'lg'
  className?: string
  [data: `data-${string}`]: unknown
}

export function TextInput({ref, label, isLabelHidden, description, isOptional, isDisabled, type = 'text', value, onChange, placeholder, startIcon, hasClear, hasAutoFocus, onEnter, onKeyDown, autoComplete, size = 'md', className, ...rest}: TextInputProps) {
  const id = useId()
  return <Field id={id} label={label} isLabelHidden={isLabelHidden} description={description} isOptional={isOptional}>
    <Input {...rest as object} id={id} ref={ref} className={className} type={type} value={value} placeholder={placeholder} prefix={isIconType(startIcon) ? <Icon icon={startIcon} color="secondary" /> : startIcon}
      allowClear={hasClear} autoFocus={hasAutoFocus} disabled={isDisabled} autoComplete={autoComplete} size={BUTTON_SIZE[size]}
      aria-label={label} onChange={event => onChange?.(event.target.value, event)} onPressEnter={onEnter} onKeyDown={onKeyDown} />
  </Field>
}

interface Option {value: string; label: ReactNode; icon?: ReactNode}
export function Selector({label, isLabelHidden, value, onChange, options, size = 'md', isDisabled, placeholder}: {
  label: string
  isLabelHidden?: boolean
  value?: string | null
  onChange?: (value: string) => void
  options: Option[]
  size?: 'sm' | 'md' | 'lg'
  isDisabled?: boolean
  placeholder?: string
}) {
  const id = useId()
  return <Field id={id} label={label} isLabelHidden={isLabelHidden}>
    <Select id={id} aria-label={label} value={value ?? undefined} onChange={next => onChange?.(next)} disabled={isDisabled} placeholder={placeholder}
      size={BUTTON_SIZE[size]} popupMatchSelectWidth={false} style={{minWidth: 120}}
      options={options.map(option => ({value: option.value, label: option.icon ? <Flex gap={8} align="center">{option.icon}{option.label}</Flex> : option.label}))} />
  </Field>
}

export function Switch({label, isLabelHidden, value, onChange, changeAction, isLoading, size = 'md', isDisabled, description}: {
  label: string
  isLabelHidden?: boolean
  value: boolean
  onChange?: (checked: boolean) => void
  changeAction?: (checked: boolean) => unknown
  isLoading?: boolean
  size?: 'sm' | 'md'
  isDisabled?: boolean
  description?: string
}) {
  const [pending, setPending] = useState(false)
  const control = <AntSwitch checked={value} loading={isLoading || pending} size={size === 'sm' ? 'small' : 'default'} disabled={isDisabled} aria-label={label}
    onChange={checked => {
      onChange?.(checked)
      const result = changeAction?.(checked)
      if (result instanceof Promise) { setPending(true); void result.finally(() => setPending(false)) }
    }} />
  if (isLabelHidden) return control
  return <Flex justify="space-between" align="center" gap={16}>
    <Flex vertical><Text weight="medium">{label}</Text>{description ? <Text type="supporting" color="secondary">{description}</Text> : null}</Flex>
    {control}
  </Flex>
}

export function FileInput({label, accept, onChange, changeAction, isDisabled, isLoading, description, placeholder, className, maxSize, status}: {
  label: string
  isLabelHidden?: boolean
  value?: File | File[] | null
  onChange: (file: File | File[] | null) => void
  changeAction?: (file: File | File[] | null) => Promise<void>
  accept?: string
  maxSize?: number
  isDisabled?: boolean
  isLoading?: boolean
  description?: string
  placeholder?: string
  mode?: 'dropzone' | 'input'
  status?: {type: 'error' | 'success' | 'warning'; message: string}
  statusVariant?: string
  width?: string | number
  className?: string
}) {
  return <Upload.Dragger className={className} accept={accept} multiple={false} showUploadList={false} disabled={isDisabled || isLoading}
    aria-label={label}
    beforeUpload={file => {
      if (maxSize && file.size > maxSize) return Upload.LIST_IGNORE
      onChange(file)
      void changeAction?.(file)
      return false
    }}>
    <Flex vertical align="center" gap={4} style={{padding: 16}}>
      {isLoading ? <Spin /> : null}
      <Text weight="semibold">{placeholder ?? label}</Text>
      {description ? <Text type="supporting" color="secondary">{description}</Text> : null}
      {status ? <Text type="supporting" color={status.type}>{status.message}</Text> : null}
    </Flex>
  </Upload.Dragger>
}

export const RadioIndicator = ({state, className, ...rest}: {state: 'checked' | 'unchecked'; size?: string; className?: string; [data: `data-${string}`]: unknown}) =>
  <span {...rest} className={cx('pk-radio-indicator', className)} data-state={state} aria-hidden />

/* ---------- Choices ---------- */

type ItemProps = {value: string; label?: string; isLabelHidden?: boolean; icon?: ReactNode; children?: ReactNode}
const itemsOf = (children: ReactNode) => Children.toArray(children).filter(isValidElement) as ReactElement<ItemProps>[]

export const SegmentedControlItem = (_: ItemProps) => null
export function SegmentedControl({value, onChange, label, size = 'md', children}: {value: string; onChange: (value: string) => void; label: string; size?: 'sm' | 'md'; children?: ReactNode}) {
  return <Segmented aria-label={label} value={value} onChange={next => onChange(String(next))} size={size === 'sm' ? 'small' : 'middle'}
    options={itemsOf(children).map(({props}) => ({value: props.value, icon: props.icon, title: props.label,
      label: props.isLabelHidden ? undefined : props.label ?? props.children}))} />
}

export const Tab = (_: ItemProps & {panelId?: string}) => null
export function TabList({value, onChange, children, className, hasDivider: _hasDivider, ...rest}: {value: string; onChange: (value: string) => void; children?: ReactNode; className?: string; hasDivider?: boolean; role?: string; 'aria-label'?: string}) {
  return <Tabs {...rest as object} className={cx('pk-tabs', className)} activeKey={value} onChange={onChange}
    items={itemsOf(children).map(({props}) => ({key: props.value, label: props.label ?? props.children, icon: props.icon}))} />
}

/* ---------- Lists ---------- */

export function List({header, density = 'balanced', hasDividers, className, children}: {header?: ReactNode; density?: 'compact' | 'balanced' | 'spacious'; hasDividers?: boolean; className?: string; children?: ReactNode; number?: boolean; icon?: ReactNode}) {
  const items = <ul className={cx('pk-list pk-list__items', className)} data-density={density} data-dividers={hasDividers || undefined}>{children}</ul>
  if (!header) return items
  return <div className="pk-list-group"><div className="pk-list__header">{header}</div>{items}</div>
}

export interface ListItemProps {
  label: ReactNode
  description?: ReactNode
  startContent?: ReactNode
  endContent?: ReactNode
  onClick?: (event: MouseEvent) => void
  isSelected?: boolean
  isDisabled?: boolean
  textWrap?: string
  rank?: ReactNode
  as?: 'li' | 'div'
  className?: string
}

export function ListItem({label, description, startContent, endContent, onClick, isSelected, isDisabled, rank, as = 'li', className}: ListItemProps) {
  const Element = as
  const main = <>
    {rank !== undefined ? <span className="pk-list-item__rank">{rank}</span> : null}
    {startContent ? <span className="pk-list-item__start">{startContent}</span> : null}
    <span className="pk-list-item__body">
      <span className="pk-list-item__label">{label}</span>
      {description ? <span className="pk-list-item__description">{description}</span> : null}
    </span>
  </>
  // The row's own action wraps its content; end content (other buttons) stays beside it, never inside.
  return <Element className={cx('pk-list-item', className)} data-selected={isSelected || undefined} data-interactive={onClick ? true : undefined}>
    <div className="pk-list-item__action">
      {onClick ? <button type="button" className="pk-list-item__main" disabled={isDisabled} onClick={onClick}>{main}</button>
        : <div className="pk-list-item__main">{main}</div>}
      {endContent ? <span className="pk-list-item__end">{endContent}</span> : null}
    </div>
  </Element>
}
export const Item = ListItem

export type {CSSProperties}
