import {useCallback, useEffect, useMemo, useRef, useState} from 'react'
import {createPortal} from 'react-dom'
import type {CSSProperties, ReactElement, ReactNode} from 'react'
import {Alert, App, Button as AntButton, Dropdown, Flex, Input, Modal, Popover, Tooltip as AntTooltip} from 'antd'
import type {InputRef, MenuProps} from 'antd'
import {X} from 'lucide-react'
import {Button, type ButtonProps, type ButtonVariant} from './controls'
import {Text} from './typography'
import {VisuallyHidden} from './layout'

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

export function Dialog({isOpen, onOpenChange, label, purpose = 'info', width, maxHeight, padding = 5, className, style, children}: {
  style?: CSSProperties
  isOpen: boolean
  onOpenChange: (isOpen: boolean) => unknown
  label?: string
  purpose?: 'info' | 'form' | 'required'
  width?: number | string
  maxHeight?: number | string
  padding?: number
  variant?: string
  className?: string
  children: ReactNode
}) {
  const dismissible = purpose !== 'required'
  if (typeof document === 'undefined') return isOpen ? <div role="dialog" aria-label={label} className={className}>{children}</div> : null
  return <Modal open={isOpen} title={label ? <VisuallyHidden>{label}</VisuallyHidden> : undefined} onCancel={() => dismissible && onOpenChange(false)} footer={null} closable={false} centered
    mask={{closable: dismissible}} keyboard={dismissible} width={width ?? 560} destroyOnHidden className={className}
    styles={{header: label ? {margin: 0} : undefined, container: {padding: 0, overflow: 'hidden'}, body: {padding: padding * 4, maxHeight, overflowY: 'auto', display: 'flex', flexDirection: 'column', ...style}}}>
    {children}
  </Modal>
}

/** A full-window layer that blurs the app behind it; Escape or the corner close button dismisses it. */
export function FullscreenOverlay({isOpen, onClose, label, closeLabel, closeText, className, children}: {
  isOpen: boolean
  onClose: () => void
  label: string
  closeLabel: string
  /** Visible text beside the close cross, when the cross alone would be ambiguous. */
  closeText?: string
  className?: string
  children: ReactNode
}) {
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!isOpen) return
    const previous = document.activeElement instanceof HTMLElement ? document.activeElement : null
    ref.current?.querySelector<HTMLElement>('[data-autofocus], button')?.focus()
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') { event.preventDefault(); onClose() }
    }
    window.addEventListener('keydown', onKey)
    return () => { window.removeEventListener('keydown', onKey); previous?.focus() }
  }, [isOpen, onClose])
  if (!isOpen || typeof document === 'undefined') return null
  return createPortal(<div ref={ref} role="dialog" aria-modal="true" aria-label={label} className={['pk-fullscreen-overlay', className].filter(Boolean).join(' ')}>
    <AntTooltip title={closeLabel}>
      <AntButton className="pk-fullscreen-overlay__close" type="text" size="large" icon={<X size={24} />} iconPlacement="end"
        aria-label={closeText ? undefined : closeLabel} onClick={onClose}>{closeText}</AntButton>
    </AntTooltip>
    {children}
  </div>, document.body)
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

export function AlertDialog({isOpen, onOpenChange, title, description, warning, cancelLabel = 'Cancel', actionLabel, actionVariant = 'destructive', isActionLoading, onAction, width}: {
  isOpen: boolean
  onOpenChange: (isOpen: boolean) => unknown
  title: string
  description: string
  /** An exceptional consequence the user must see before confirming. */
  warning?: string
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
    <Flex vertical gap={12}>
      {warning ? <Alert type="warning" showIcon title={warning} /> : null}
      <Text color="secondary">{description}</Text>
    </Flex>
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
  return <MenuTrigger hint={label} menu={{items: menuItems(items)}} disabled={isDisabled}>
    <Button label={label} isIconOnly hasTooltip={false} variant={variant} size={size} isDisabled={isDisabled}
      icon={icon ?? <span aria-hidden style={{fontWeight: 700, letterSpacing: 1}}>⋯</span>} />
  </MenuTrigger>
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
  return <MenuTrigger hint={button.tooltip ?? button.label} disabled={button.isDisabled}
    menu={{items: items.map((item, index) => ({key: String(item.key ?? index), label: item.props.label, icon: item.props.icon, disabled: item.props.isDisabled, onClick: item.props.onClick, style: item.props.style}))}}>
    <Button {...button} hasTooltip={false} />
  </MenuTrigger>
}

/** A menu button whose hint hides while its menu is open, so it never covers the menu. */
function MenuTrigger({hint, menu, disabled, children}: {hint: ReactNode; menu: MenuProps; disabled?: boolean; children: ReactNode}) {
  const [open, setOpen] = useState(false)
  return <Dropdown menu={menu} trigger={['click']} placement="bottomRight" disabled={disabled} open={open} onOpenChange={setOpen}>
    <span><AntTooltip title={hint} open={open ? false : undefined}><span>{children}</span></AntTooltip></span>
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
