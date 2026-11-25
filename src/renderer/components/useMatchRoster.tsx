import {useId, useRef, useState, type DragEvent, type KeyboardEvent} from 'react'
import {GripVertical, RotateCcw} from 'lucide-react'
import {alignValorantMatchup, moveTeamCard} from '../matchCardOrder'
import {isConfirmedDuo, resolveMatchLayout, type MatchLayoutInput} from '../matchLayout'
import {displayText, t} from '../i18n'
import type {MatchTeam} from '../types'
import {Button, Icon, IconButton, VisuallyHidden} from '../ui'

interface RosterContext extends MatchLayoutInput {
  allowReorder?: boolean
  completed?: boolean
  matchId?: string
  map?: string
}

export interface CardReorder {
  position: number
  count: number
  selected: boolean
  dragging: boolean
  dropTarget: boolean
  instructionsId: string
  onToggle: () => void
  onKeyDown: (event: KeyboardEvent<HTMLButtonElement>) => void
  onDragStart: (event: DragEvent<HTMLButtonElement>) => void
  onDragEnd: () => void
  onDragEnter: () => void
  onDragOver: (event: DragEvent<HTMLElement>) => void
  onDrop: (event: DragEvent<HTMLElement>) => void
}

export function ReorderHandle({name, reorder}: {name: string; reorder: CardReorder}) {
  return <IconButton className="pmc-card__drag-handle" label={t("Reorder {{name}}, position {{value2}} of {{count}}", {name, value2: reorder.position + 1, count: reorder.count})} icon={<Icon icon={GripVertical} />} variant="ghost" size="sm" tooltip={t("Drag to a new position, or select and use arrow keys")} draggable aria-pressed={reorder.selected} aria-describedby={reorder.instructionsId} onClick={reorder.onToggle} onKeyDown={reorder.onKeyDown} onDragStart={reorder.onDragStart} onDragEnd={reorder.onDragEnd} />
}

export function useMatchRoster(context: RosterContext, onMove?: () => void) {
  const [manualOrder, setManualOrder] = useState<{scope: string; teams: number[][]} | null>(null)
  const [keyboardMove, setKeyboardMove] = useState<{scope: string; team: number; player: number; original: number[][]} | null>(null)
  const [dragging, setDragging] = useState<{scope: string; team: number; player: number} | null>(null)
  const [dropTarget, setDropTarget] = useState<{scope: string; team: number; player: number} | null>(null)
  const [announcement, setAnnouncement] = useState('')
  const dragSource = useRef<typeof dragging>(null)
  const instructionsId = useId()
  const layout = resolveMatchLayout(context)
  const canReorder = context.allowReorder === true && context.completed !== true
  const freeForAll = layout.kind === 'free-for-all'
  const duos = layout.kind === 'duos'
  const sortedTeams = [...layout.groups].sort((left, right) => {
    if (duos && isConfirmedDuo(left) !== isConfirmedDuo(right)) return Number(isConfirmedDuo(right)) - Number(isConfirmedDuo(left))
    return Number(right.players.some(player => player.self)) - Number(left.players.some(player => player.self))
  })
  const ownTeam = sortedTeams.find(team => (!duos || isConfirmedDuo(team)) && team.players.some(player => player.self))
  const reorderableTeam = (team: MatchTeam) => canReorder && team.players.length > 1 && (!duos || isConfirmedDuo(team))
  const alignedPlayers = layout.canAlignRoles
    ? alignValorantMatchup(sortedTeams[0].players, sortedTeams[1].players)
    : undefined
  const suggestedOrder = sortedTeams.map((team, teamIndex) => {
    const players = freeForAll
      ? [...team.players].sort((left, right) => context.game === 'Teamfight Tactics'
        ? ((context.completed ? left.stats?.placement : left.stats?.standing ?? left.stats?.placement) || Infinity) - ((context.completed ? right.stats?.placement : right.stats?.standing ?? right.stats?.placement) || Infinity)
        : (right.stats?.kills ?? 0) - (left.stats?.kills ?? 0) || (left.stats?.deaths ?? 0) - (right.stats?.deaths ?? 0))
      : alignedPlayers?.[teamIndex] ?? team.players
    return players.map(player => team.players.indexOf(player))
  })
  // Stable across stat refreshes and agent selection. New match/roster identity
  // invalidates local arrangements so positions never transfer to other people.
  const scope = JSON.stringify([context.game, context.matchId, context.map, context.phase, layout.kind, canReorder,
    sortedTeams.map(team => [team.name, team.players.map(player => [player.riotId, player.name, player.self])])])
  const orders = canReorder && manualOrder?.scope === scope ? manualOrder.teams : suggestedOrder
  const hasCustomOrder = orders.some((order, team) => order.some((player, position) => player !== suggestedOrder[team][position]))
  const selected = keyboardMove?.scope === scope ? keyboardMove : null
  const partyCounts = new Map<string, number>()
  for (const team of sortedTeams) for (const player of team.players) if (player.partyId) partyCounts.set(player.partyId, (partyCounts.get(player.partyId) ?? 0) + 1)
  const partyGroups = new Map([...partyCounts].filter(([, count]) => count >= 2).map(([id], index) => [id, {color: ['yellow', 'purple', 'blue'][index % 3], number: index + 1}]))

  const finishDrag = () => { dragSource.current = null; setDragging(null); setDropTarget(null) }
  const move = (team: number, player: number, target: number) => {
    if (!canReorder) return
    const from = orders[team].indexOf(player)
    if (from < 0 || target < 0 || target >= orders[team].length || target === from) return
    setManualOrder({scope, teams: moveTeamCard(orders, {team, index: from}, {team, index: target})})
    onMove?.()
    setAnnouncement(t('Card moved to position {{position}} of {{count}}.', {position: target + 1, count: orders[team].length}))
  }
  const reorder = (team: number, player: number, position: number): CardReorder => {
    const isSelected = selected?.team === team && selected.player === player
    return {
      position,
      count: orders[team].length,
      selected: isSelected,
      dragging: dragging?.scope === scope && dragging.team === team && dragging.player === player,
      dropTarget: dropTarget?.scope === scope && dropTarget.team === team && dropTarget.player === player,
      instructionsId,
      onToggle: () => {
        onMove?.()
        if (isSelected) { setKeyboardMove(null); setAnnouncement(t('Card placed at position {{position}}.', {position: position + 1})); return }
        setKeyboardMove({scope, team, player, original: orders.map(order => [...order])})
        setAnnouncement(t('Card selected at position {{position}}. Use arrow keys to move, Enter to place, or Escape to cancel.', {position: position + 1}))
      },
      onKeyDown: event => {
        if (!isSelected) return
        if (event.key === 'Escape') {
          event.preventDefault()
          setManualOrder({scope, teams: selected.original})
          setKeyboardMove(null)
          setAnnouncement('Move cancelled. Previous card order restored.')
        } else {
          const target = event.key === 'ArrowLeft' || event.key === 'ArrowUp' ? position - 1
            : event.key === 'ArrowRight' || event.key === 'ArrowDown' ? position + 1
              : event.key === 'Home' ? 0 : event.key === 'End' ? orders[team].length - 1 : undefined
          if (target === undefined) return
          event.preventDefault()
          move(team, player, target)
        }
        const handle = event.currentTarget
        requestAnimationFrame(() => handle.focus({preventScroll: true}))
      },
      onDragStart: event => {
        const source = {scope, team, player}
        dragSource.current = source
        setDragging(source)
        setKeyboardMove(null)
        onMove?.()
        event.dataTransfer.effectAllowed = 'move'
        event.dataTransfer.setData('application/x-peaks-player-card', '1')
        const card = event.currentTarget.closest('.pmc-card, [data-roster-row]')
        if (card) {
          const bounds = card.getBoundingClientRect()
          event.dataTransfer.setDragImage(card, event.clientX - bounds.left, event.clientY - bounds.top)
        }
      },
      onDragEnd: finishDrag,
      onDragEnter: () => {
        const source = dragSource.current
        setDropTarget(source?.scope === scope && source.team === team && source.player !== player ? {scope, team, player} : null)
      },
      onDragOver: event => {
        const source = dragSource.current
        if (source?.scope !== scope || source.team !== team) return
        event.preventDefault()
        event.dataTransfer.dropEffect = 'move'
      },
      onDrop: event => {
        const source = dragSource.current
        if (source?.scope !== scope || source.team !== team) return
        event.preventDefault()
        move(team, source.player, position)
        finishDrag()
      },
    }
  }

  const resetOrder = hasCustomOrder ? <Button label={t("Reset order")} icon={<Icon icon={RotateCcw} />} size="sm" variant="ghost" onClick={() => { setManualOrder(null); setKeyboardMove(null); finishDrag(); setAnnouncement('Suggested card order restored.') }} /> : null

  const instructions = <>
    {canReorder ? <VisuallyHidden id={instructionsId}>{freeForAll ? t('Drag cards within this lobby.') : t('Drag cards within the same team.')} {t('With a keyboard, press Enter or Space to select a card, use arrow keys to move, then Enter or Space to place. Escape cancels the move.')}</VisuallyHidden> : null}
    {canReorder ? <VisuallyHidden role="status" aria-live="polite" aria-atomic="true">{displayText(announcement)}</VisuallyHidden> : null}
  </>
  return {layout, canReorder, freeForAll, duos, sortedTeams, ownTeam, reorderableTeam, orders, hasCustomOrder, partyGroups, reorder, resetOrder, instructions}
}
