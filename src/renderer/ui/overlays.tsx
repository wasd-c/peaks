import {useCallback, useEffect, useMemo, useRef, useState} from 'react'
import type {CSSProperties, ReactElement, ReactNode} from 'react'
import {App, Button as AntButton, Dropdown, Flex, Input, Modal, Popover, Tooltip as AntTooltip} from 'antd'
import type {InputRef, MenuProps} from 'antd'
import {X} from 'lucide-react'
import {Button, type ButtonProps, type ButtonVariant} from './controls'
import {Text} from './typography'

type Placement = 'above' | 'below' | 'start' | 'end'
const PLACEMENT = {above: 'top', below: 'bottom', start: 'left', end: 'right'} as const

export function Tooltip({content, children, placement, delay, isOpen, onOpenChange}: {
  content: ReactNode
  isOpen?: boolean
  onOpenChange?: (isOpen: boolean) => void
  children: ReactNode
  placement?: Placement
  delay?: number
  hasHoverIndication?: boolean
  focusTrigger?: string
  touchTrigger?: string
}) {
  return <AntTooltip title={content} open={isOpen} onOpenChange={onOpenChange} placement={placement ? PLACEMENT[placement] : undefined} mouseEnterDelay={delay === undefined ? 0.1 : delay / 1000}>
    {children as ReactElement}
  </AntTooltip>
}

export function HoverCard({content, children, placement = 'end', className, label}: {
  content: ReactNode
  children: ReactNode
  placement?: Placement
  alignment?: 'start' | 'center' | 'end'
  className?: string
  label?: string
  hasHoverIndication?: boolean
  focusTrigger?: string
  touchTrigger?: string
}) {
  return <Popover content={content} placement={PLACEMENT[placement]} classNames={{root: className}} aria-label={label}
    trigger={['hover', 'focus', 'click']} mouseEnterDelay={0.15} styles={{container: {padding: 0}}}>
    {children as ReactElement}
  </Popover>
}

/* ---------- Dialogs ---------- */

export function Dialog({isOpen, onOpenChange, purpose = 'info', width, maxHeight, padding = 5, className, style, children}: {
  style?: CSSProperties
  isOpen: boolean
  onOpenChange: (isOpen: boolean) => unknown
  purpose?: 'info' | 'form' | 'required'
  width?: number | string
  maxHeight?: number | string
  padding?: number
  variant?: string
  className?: string
  children: ReactNode
}) {
  const dismissible = purpose !== 'required'
  if (typeof document === 'undefined') return isOpen ? <div role="dialog" className={className}>{children}</div> : null
  return <Modal open={isOpen} onCancel={() => dismissible && onOpenChange(false)} footer={null} closable={false} centered
    mask={{closable: dismissible}} keyboard={dismissible} width={width ?? 560} destroyOnHidden className={className}
    styles={{container: {padding: 0, overflow: 'hidden'}, body: {padding: padding * 4, maxHeight, overflowY: 'auto', display: 'flex', flexDirection: 'column', ...style}}}>
    {children}
  </Modal>
}

export function DialogHeader({title, subtitle, onOpenChange, startContent, endContent}: {
  title: string
  subtitle?: string
  onOpenChange?: (isOpen: boolean) => unknown
  startContent?: ReactNode
  endContent?: ReactNode
  hasDivider?: boolean
}) {
  return <Flex align="center" gap={12} className="pk-dialog-header" style={{padding: 16}}>
    {startContent}
    <Flex vertical style={{flex: 1, minWidth: 0}}>
      <Text type="large" weight="semibold" role="heading" aria-level={2}>{title}</Text>
      {subtitle ? <Text type="supporting" color="secondary">{subtitle}</Text> : null}
    </Flex>
    {endContent}
    {onOpenChange ? <AntButton type="text" icon={<X size={16} />} aria-label="Close" onClick={() => onOpenChange(false)} /> : null}
  </Flex>
}

export function AlertDialog({isOpen, onOpenChange, title, description, cancelLabel = 'Cancel', actionLabel, actionVariant = 'destructive', isActionLoading, onAction, width}: {
  isOpen: boolean
  onOpenChange: (isOpen: boolean) => unknown
  title: string
  description: string
  cancelLabel?: string
  actionLabel: string
  actionVariant?: ButtonVariant
  isActionLoading?: boolean
  onAction: () => unknown
  width?: number | string
}) {
  return <Modal open={isOpen} title={title} onCancel={() => onOpenChange(false)} width={width ?? 440} centered destroyOnHidden
    footer={<Flex justify="flex-end" gap={8}>
      <Button label={cancelLabel} variant="secondary" isDisabled={isActionLoading} onClick={() => onOpenChange(false)} />
      <Button label={actionLabel} variant={actionVariant} isLoading={isActionLoading} onClick={() => void onAction()} />
    </Flex>}>
    <Text color="secondary">{description}</Text>
  </Modal>
}

/* ---------- Menus ---------- */

export interface MenuOption {
  id: string
  label: ReactNode
  description?: ReactNode
  icon?: ReactNode
  onClick?: () => void
  isDisabled?: boolean
  variant?: 'default' | 'destructive'
}

const menuItems = (items: MenuOption[]): MenuProps['items'] => items.map(item => ({
  key: item.id, icon: item.icon, disabled: item.isDisabled, danger: item.variant === 'destructive', onClick: item.onClick,
  label: item.description ? <Flex vertical><span>{item.label}</span><Text type="supporting" color="secondary">{item.description}</Text></Flex> : item.label,
}))

export function MoreMenu({items, label = 'More actions', icon, isDisabled, variant = 'ghost', size}: {
  items: MenuOption[]
  label?: string
  icon?: ReactNode
  isDisabled?: boolean
  variant?: ButtonVariant
  size?: 'sm' | 'md' | 'lg'
  alignment?: string
  placement?: string
}) {
  return <Dropdown menu={{items: menuItems(items)}} trigger={['click']} placement="bottomRight" disabled={isDisabled}>
    <span><Button label={label} isIconOnly variant={variant} size={size} isDisabled={isDisabled}
      icon={icon ?? <span aria-hidden style={{fontWeight: 700, letterSpacing: 1}}>⋯</span>} /></span>
  </Dropdown>
}

export interface DropdownMenuItemProps {
  label: ReactNode
  onClick?: () => void
  isDisabled?: boolean
  icon?: ReactNode
  style?: CSSProperties
}
export const DropdownMenuItem = (_: DropdownMenuItemProps) => null

export function DropdownMenu({button, children}: {button: Omit<ButtonProps, 'label'> & {label: string}; children?: ReactNode; presentation?: string; alignment?: string; hasChevron?: boolean; menuWidth?: string}) {
  const items = (Array.isArray(children) ? children : [children]).flat().filter(Boolean) as ReactElement<DropdownMenuItemProps>[]
  return <Dropdown trigger={['click']} placement="bottomRight" disabled={button.isDisabled}
    menu={{items: items.map((item, index) => ({key: String(item.key ?? index), label: item.props.label, icon: item.props.icon, disabled: item.props.isDisabled, onClick: item.props.onClick, style: item.props.style}))}}>
    <span><Button {...button} /></span>
  </Dropdown>
}

/* ---------- Command palette ---------- */

export interface SearchItem {id: string; label: string; auxiliaryData?: {group?: string}}
export interface SearchSource {items: SearchItem[]}
export const createStaticSource = (items: SearchItem[]): SearchSource => ({items})

export function CommandPalette({isOpen, onOpenChange, searchSource, onValueChange, label, emptySearchText}: {
  isOpen: boolean
  onOpenChange: (isOpen: boolean) => void
  searchSource: SearchSource
  onValueChange: (id: string) => void
  label: string
  emptySearchText?: string
}) {
  const [query, setQuery] = useState('')
  const [active, setActive] = useState(0)
  const input = useRef<InputRef>(null)
  const results = useMemo(() => {
    const needle = query.trim().toLocaleLowerCase()
    return searchSource.items.filter(item => !needle || item.label.toLocaleLowerCase().includes(needle))
  }, [query, searchSource])
  useEffect(() => { if (isOpen) { setQuery(''); setActive(0) } }, [isOpen])
  const choose = (item?: SearchItem) => { if (item) onValueChange(item.id) }
  let group: string | undefined
  return <Modal open={isOpen} onCancel={() => onOpenChange(false)} footer={null} closable={false} width={560} destroyOnHidden
    afterOpenChange={open => open && input.current?.focus()} styles={{body: {padding: 0}}} aria-label={label}>
    <Input ref={input} variant="borderless" size="large" placeholder={label} value={query} aria-label={label}
      style={{padding: 16, borderBottom: '1px solid var(--color-border)'}}
      onChange={event => { setQuery(event.target.value); setActive(0) }}
      onKeyDown={event => {
        if (event.key === 'ArrowDown') { event.preventDefault(); setActive(index => Math.min(results.length - 1, index + 1)) }
        if (event.key === 'ArrowUp') { event.preventDefault(); setActive(index => Math.max(0, index - 1)) }
        if (event.key === 'Enter') choose(results[active])
      }} />
    <div role="listbox" aria-label={label} className="pk-command-results">
      {results.length ? results.map((item, index) => {
        const heading = item.auxiliaryData?.group !== group ? (group = item.auxiliaryData?.group) : undefined
        return <div key={item.id}>
          {heading ? <Text type="supporting" color="secondary" className="pk-command-group">{heading}</Text> : null}
          <button type="button" role="option" aria-selected={index === active} className="pk-command-item"
            onMouseEnter={() => setActive(index)} onClick={() => choose(item)}>{item.label}</button>
        </div>
      }) : <Text color="secondary" className="pk-command-empty">{emptySearchText}</Text>}
    </div>
  </Modal>
}

/* ---------- Toasts ---------- */

export interface ToastOptions {body: ReactNode; type?: 'info' | 'success' | 'warning' | 'error'; uniqueID?: string; isAutoHide?: boolean; title?: ReactNode}

export function useToast() {
  const {notification} = App.useApp()
  return useCallback((toast: ToastOptions) => {
    notification[toast.type ?? 'info']({
      key: toast.uniqueID, title: toast.title ?? toast.body, description: toast.title ? toast.body : undefined,
      placement: 'bottomRight', duration: toast.isAutoHide === false ? 0 : 6,
    })
  }, [notification])
}
