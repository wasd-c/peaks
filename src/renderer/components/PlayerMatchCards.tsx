import {useId, useRef, useState, type Dispatch, type DragEvent, type KeyboardEvent, type SetStateAction} from 'react'
import {Button} from '@astryxdesign/core/Button'
import {Card} from '@astryxdesign/core/Card'
import {Grid, GridSpan} from '@astryxdesign/core/Grid'
import {Heading} from '@astryxdesign/core/Heading'
import {HStack} from '@astryxdesign/core/HStack'
import {Icon} from '@astryxdesign/core/Icon'
import {IconButton} from '@astryxdesign/core/IconButton'
import {Skeleton} from '@astryxdesign/core/Skeleton'
import {Text} from '@astryxdesign/core/Text'
import {Token} from '@astryxdesign/core/Token'
import {Tooltip} from '@astryxdesign/core/Tooltip'
import {VStack} from '@astryxdesign/core/VStack'
import {VisuallyHidden} from '@astryxdesign/core/VisuallyHidden'
import {ArrowUpRight, Check, Crown, EyeOff, GripVertical, RotateCcw, Shield, UsersRound} from 'lucide-react'
import {hasExactValorantRankAsset, rankAsset, valorantAgentName, valorantAgentPortraitAsset} from '../assets'
import {historicalPerformanceTags, playerPerformanceTags, type PerformanceTag} from '../matchAnalytics'
import {alignValorantMatchup, moveTeamCard} from '../matchCardOrder'
import {isConfirmedDuo, matchGridColumns, resolveMatchLayout} from '../matchLayout'
import {matchPlayerProfile} from '../playerProfiles'
import type {Game, MatchPlayer, MatchTeam, Player, PlayerStats, SessionPhase} from '../types'
import {usePlayerPrivacy} from './PlayerPrivacy'

interface PlayerMatchCardsProps {
  teams: MatchTeam[]
  game?: Game
  region?: string
  map?: string
  mode?: string
  queueId?: string
  modeId?: string
  gameMode?: string
  matchId?: string
  label: string
  result?: string
  freeForAll?: boolean
  teamMode?: 'duos'
  completed?: boolean
  phase?: SessionPhase
  allowReorder?: boolean
  onSelectPlayer: (player: Player) => void
}

const validNumber = (value: unknown): value is number => typeof value === 'number' && Number.isFinite(value) && value >= 0
const hasNumbers = (stats?: PlayerStats) => Boolean(stats && Object.entries(stats).some(([key, value]) => !['matchesPlayed', 'wins', 'observedAt'].includes(key) && validNumber(value)))
const numeric = (value?: number, decimals = 0) => validNumber(value) ? value.toLocaleString(undefined, {maximumFractionDigits: decimals}) : '—'
const average = (value?: number, count?: number) => validNumber(value) ? numeric(count && count > 0 ? value / count : value, count && count > 1 ? 1 : 0) : '—'
const ratio = (numerator?: number, denominator?: number, decimals = 0) => validNumber(numerator) && validNumber(denominator) && denominator > 0 ? numeric(numerator / denominator, decimals) : '—'

function headshotRate(stats?: PlayerStats) {
  if (!stats || ![stats.headshots, stats.bodyshots, stats.legshots].every(validNumber)) return '—'
  const hits = stats.headshots! + stats.bodyshots! + stats.legshots!
  return hits > 0 ? `${Math.round(stats.headshots! / hits * 100)}%` : '—'
}

function statsRows(overall?: PlayerStats, match?: PlayerStats, preserveRowsFor?: Game) {
  const count = overall?.matchesPlayed
  const rows = [
    {label: 'HP', overall: '—', match: numeric(match?.health, 1)},
    {label: 'Standing', overall: '—', match: validNumber(match?.standing) ? `#${numeric(match.standing)}` : '—'},
    {label: 'Board units', overall: '—', match: numeric(match?.boardUnits)},
    {label: 'Augments', overall: '—', match: numeric(match?.augmentCount)},
    {label: 'K/D', overall: ratio(overall?.kills, overall?.deaths, 2), match: ratio(match?.kills, match?.deaths, 2)},
    {label: 'ACS', overall: ratio(overall?.combatScore, overall?.roundsPlayed), match: ratio(match?.combatScore, match?.roundsPlayed)},
    {label: 'ADR', overall: ratio(overall?.damage, overall?.roundsPlayed), match: ratio(match?.damage, match?.roundsPlayed)},
    {label: 'HS%', overall: headshotRate(overall), match: headshotRate(match)},
    ...(['kills', 'deaths', 'assists'] as const).map(key => ({label: `${key[0].toUpperCase()}${key.slice(1)}`, overall: average(overall?.[key], count), match: numeric(match?.[key])})),
    ...([
      ['gold', 'Gold'], ['minions', 'CS'], ['vision', 'Vision'], ['placement', 'Placement'], ['playersEliminated', 'Eliminations'], ['level', 'Level'],
    ] as const).map(([key, label]) => ({label, overall: average(overall?.[key], count), match: numeric(match?.[key])})),
  ]
  if ((overall?.combatScore != null && !overall.roundsPlayed) || (match?.combatScore != null && !match.roundsPlayed)) {
    rows.push({label: 'Score', overall: !overall?.roundsPlayed ? average(overall?.combatScore, count) : '—', match: !match?.roundsPlayed ? numeric(match?.combatScore) : '—'})
  }
  if ((overall?.damage != null && !overall.roundsPlayed) || (match?.damage != null && !match.roundsPlayed)) {
    rows.push({label: 'Damage', overall: !overall?.roundsPlayed ? average(overall?.damage, count) : '—', match: !match?.roundsPlayed ? numeric(match?.damage) : '—'})
  }
  const reservedLabels = preserveRowsFor === 'VALORANT' ? ['K/D', 'ACS', 'ADR', 'HS%', 'Kills', 'Deaths', 'Assists']
    : preserveRowsFor === 'League of Legends' ? ['K/D', 'Kills', 'Deaths', 'Assists', 'Gold', 'CS', 'Vision']
      : preserveRowsFor === 'Teamfight Tactics' ? ['Placement', 'Eliminations', 'Gold', 'Level'] : []
  return rows.filter(row => reservedLabels.includes(row.label) || row.overall !== '—' || row.match !== '—')
}

function StatValue({value, loading = false, index = 0}: {value: string; loading?: boolean; index?: number}) {
  if (loading && value === '—') return (
    <HStack className="pmc-stat-placeholder" role="cell" aria-label="Loading" justify="end" align="center">
      <Skeleton className="pmc-stat-skeleton" width={`var(--spacing-${[7, 6, 8, 5][index % 4]})`} height="var(--spacing-2)" radius="none" index={index} />
    </HStack>
  )
  return <Text className="pmc-stat-value" role="cell" hasTabularNumbers weight="medium">{value}</Text>
}

function CardRank({game, rank, caption}: {game?: Game; rank?: string; caption: string}) {
  const label = rank?.trim() || 'Unavailable'
  const tier = label.toLowerCase().split(' ')[0]
  const knownRank = game === 'VALORANT' ? hasExactValorantRankAsset(rank)
    : ['iron', 'bronze', 'silver', 'gold', 'platinum', 'emerald', 'diamond', 'master', 'grandmaster', 'challenger'].includes(tier)
  const asset = game && rank && knownRank ? rankAsset(game, label) : undefined
  return (
    <VStack className="pmc-rank" align="center" gap={1}>
      {asset ? <img className="pmc-rank__image" alt={`${label} rank emblem`} src={asset} /> : <HStack className="pmc-rank__placeholder" align="center" justify="center"><Icon icon={Shield} color="secondary" /></HStack>}
      <Text className="pmc-rank__name" maxLines={1} type="supporting">{label}</Text>
      <Text className="pmc-rank__caption" type="supporting">{caption}</Text>
    </VStack>
  )
}

interface TagSelection {
  activeTagId: string | null
  setActiveTagId: Dispatch<SetStateAction<string | null>>
}

function TagExplanation({tag, source, activeTagId, setActiveTagId}: {tag: PerformanceTag; source: 'past' | 'match'} & TagSelection) {
  const tagId = useId()
  return <Tooltip
    content={`${source === 'past' ? 'Past games' : 'This match'} · ${tag.detail}`}
    hasHoverIndication={false}
    isOpen={activeTagId === tagId}
    onOpenChange={open => setActiveTagId(current => open ? tagId : current === tagId ? null : current)}>
    <Token className={`pmc-tag pmc-tag--${source}`} description={tag.detail} label={tag.label} onClick={() => setActiveTagId(current => current === tagId ? null : tagId)} size="sm" />
  </Tooltip>
}

interface CardReorder {
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

function PlayerCard({player, index, team, tone, party, context, tagSelection, reorder, onSelectPlayer}: {
  player: MatchPlayer
  index: number
  team: MatchTeam
  tone: 'ally' | 'self' | 'enemy' | 'neutral' | 'ffa'
  party?: {color: string; number: number}
  context: Omit<PlayerMatchCardsProps, 'teams' | 'onSelectPlayer'>
  tagSelection: TagSelection
  reorder?: CardReorder
  onSelectPlayer: (player: Player) => void
}) {
  const {displayName} = usePlayerPrivacy()
  const statsStatusId = useId()
  const beforeGame = !context.completed && Boolean(context.phase && context.phase !== 'live')
  const inParty = Boolean(context.phase && ['lobby', 'matchmaking', 'readycheck'].includes(context.phase))
  const statsLoading = player.statsLoading === true && !player.hidden
  const name = displayName(player.hidden ? `Hidden player ${index + 1}` : player.riotId ?? player.name)
  const profilePlayer = beforeGame ? {...player, stats: undefined, score: undefined} : player
  const profile = context.game ? matchPlayerProfile(profilePlayer, {...context, game: context.game, team: team.name}) : null
  const portrait = context.game === 'VALORANT' ? valorantAgentPortraitAsset(player.agent) : undefined
  const rosterCard = context.game === 'League of Legends' || context.game === 'Teamfight Tactics'
  const agent = context.game === 'VALORANT' ? valorantAgentName(player.agent) : player.agent
  const character = agent || (context.game === 'Teamfight Tactics' || inParty ? undefined
    : context.game === 'League of Legends' ? beforeGame ? 'Choosing champion' : 'Champion unavailable'
      : beforeGame ? 'Choosing agent' : 'Agent unavailable')
  const identityDetails = [character, player.accountLevel != null ? `Level ${player.accountLevel}` : undefined].filter(Boolean)
  const role = player.role ? ({top: 'Top', jungle: 'Jungle', middle: 'Mid', mid: 'Mid', bottom: 'Bot', utility: 'Support', support: 'Support'}[player.role.toLowerCase()] ?? player.role) : undefined
  const matchStats = !beforeGame && hasNumbers(player.stats) ? player.stats : undefined
  const overallStats = hasNumbers(player.overallStats) ? player.overallStats : undefined
  const rows = statsRows(overallStats, matchStats, statsLoading || (context.game === 'VALORANT' && Boolean(overallStats || matchStats)) ? context.game : undefined)
  const pastTags = context.game ? historicalPerformanceTags(player, context.game) : []
  const matchTags = !beforeGame && context.game ? playerPerformanceTags(player, context.game) : []
  const source = overallStats?.matchesPlayed
    ? `Recent ${overallStats.matchesPlayed} ${overallStats.matchesPlayed === 1 ? 'game' : 'games'} · kills, deaths, and assists averaged per game`
    : statsLoading ? 'Fetching player statistics' : 'Overall statistics are unavailable'
  const partner = tone === 'ally' && context.teamMode === 'duos'
  const snapshotTime = !context.completed && context.game === 'Teamfight Tactics' && validNumber(matchStats?.observedAt)
    ? new Date(matchStats.observedAt * 1000).toLocaleTimeString(undefined, {hour: '2-digit', minute: '2-digit', second: '2-digit'}) : undefined

  return (
    <Card className={`pmc-card pmc-card--${tone}${rosterCard ? ' pmc-card--roster' : ''}`} data-party={party?.color} data-dragging={reorder?.dragging || reorder?.selected ? 'true' : undefined} data-drop-target={reorder?.dropTarget ? 'true' : undefined} onDragEnter={reorder?.onDragEnter} onDragOver={reorder?.onDragOver} onDrop={reorder?.onDrop} padding={0} role="group" aria-busy={statsLoading} aria-describedby={statsLoading ? statsStatusId : undefined} aria-label={`${name}, ${tone === 'self' ? 'you' : tone === 'ally' ? 'ally' : tone === 'enemy' ? 'opponent' : 'player'}${party ? `, party ${party.number}` : ''}`}>
      {portrait ? <img className="pmc-card__portrait" src={portrait} alt="" aria-hidden="true" /> : null}
      <VStack className="pmc-card__content" gap={4} padding={4}>
        <VStack className="pmc-card__identity" gap={1}>
          <HStack align="center" justify="between" gap={2}>
            <Text className="pmc-card__side" type="supporting">{player.self ? 'YOU' : player.hidden ? 'PRIVATE PLAYER' : partner ? 'PARTNER' : tone === 'ally' ? 'ALLY' : tone === 'enemy' ? 'OPPONENT' : 'PLAYER'}</Text>
            <HStack align="center" gap={1}>
              {party ? <Tooltip content={`Party ${party.number} · players with this top border are grouped`} hasHoverIndication={false}><HStack className="pmc-card__party" align="center" gap={1}><Icon className="pmc-card__party-icon" icon={UsersRound} label={`Party ${party.number}`} /><Text className="pmc-card__party-number" type="supporting">{String(party.number).padStart(2, '0')}</Text></HStack></Tooltip> : null}
              {reorder ? <IconButton className="pmc-card__drag-handle" label={`Reorder ${name}, position ${reorder.position + 1} of ${reorder.count}`} icon={<Icon icon={GripVertical} />} variant="ghost" size="sm" tooltip="Drag to a new position, or select and use arrow keys" draggable aria-pressed={reorder.selected} aria-describedby={reorder.instructionsId} onClick={reorder.onToggle} onKeyDown={reorder.onKeyDown} onDragStart={reorder.onDragStart} onDragEnd={reorder.onDragEnd} /> : null}
            </HStack>
          </HStack>
          {profile ? <Button className="pmc-card__name-button" label={name} onClick={() => onSelectPlayer(profile)} variant="ghost" size="sm" endContent={<Icon icon={ArrowUpRight} />}><Text className="pmc-card__name" maxLines={1} weight="bold">{name}</Text></Button> : <Text className="pmc-card__name" maxLines={1} weight="bold">{name}</Text>}
          {identityDetails.length > 0 ? <Text className="pmc-card__agent" type="supporting" maxLines={1}>{identityDetails.join(' · ')}</Text> : null}
          {player.leader || (beforeGame && player.ready != null) || role ? <HStack gap={1} wrap="wrap">
            {player.leader && inParty ? <Token label="Leader" icon={<Icon icon={Crown} />} size="sm" /> : null}
            {beforeGame && context.phase !== 'readycheck' && player.ready != null ? <Token label={player.ready ? 'Ready' : 'Not ready'} icon={player.ready ? <Icon icon={Check} /> : undefined} size="sm" /> : null}
            {role ? <Token label={role} size="sm" /> : null}
          </HStack> : null}
        </VStack>

        <Grid className="pmc-card__ranks" columns={2} gap={2}>
          <CardRank game={context.game} rank={player.currentRank ?? player.rank} caption={context.completed && !player.currentRank ? 'Match rank' : 'Current'} />
          <CardRank game={context.game} rank={player.peakRank} caption={player.peakRankSeason ?? 'Peak'} />
        </Grid>

        {(pastTags.length > 0 || matchTags.length > 0) ? <VStack className="pmc-card__tags" gap={2}>
          {pastTags.length > 0 ? <HStack gap={1} wrap="wrap" aria-label="Tags from past games">{pastTags.map(tag => <TagExplanation key={tag.label} tag={tag} source="past" {...tagSelection} />)}</HStack> : null}
          {matchTags.length > 0 ? <HStack gap={1} wrap="wrap" aria-label="Tags earned this match">{matchTags.map(tag => <TagExplanation key={tag.label} tag={tag} source="match" {...tagSelection} />)}</HStack> : null}
        </VStack> : null}

        {statsLoading ? <VisuallyHidden id={statsStatusId} role="status" aria-live="off">Fetching stats</VisuallyHidden> : null}

        {rows.length > 0 ? <VStack className="pmc-card__stats" gap={1} role="table" aria-label={`${name} statistics`} aria-busy={statsLoading}>
          <Grid className="pmc-stat-row pmc-stat-row--header" columns={matchStats ? 3 : 2} gap={2} role="row">
            <Text role="columnheader" type="supporting">Stats</Text>
            <Tooltip content={source} hasHoverIndication={false}><Text role="columnheader" type="supporting">Overall</Text></Tooltip>
            {matchStats ? <Text role="columnheader" type="supporting">Match</Text> : null}
          </Grid>
          {rows.map((row, index) => <Grid className="pmc-stat-row" columns={matchStats ? 3 : 2} gap={2} key={row.label} role="row">
            {row.label === 'Standing' ? <Tooltip content="Current position in the lobby, not the final placement." hasHoverIndication={false}><Text role="rowheader" type="supporting">{row.label}</Text></Tooltip> : <Text role="rowheader" type="supporting">{row.label}</Text>}
            <StatValue value={row.overall} loading={statsLoading} index={index} />
            {matchStats ? <Text role="cell" hasTabularNumbers weight="semibold">{row.match}</Text> : null}
          </Grid>)}
          <VStack className="pmc-card__source" gap={1}>
            {overallStats?.matchesPlayed ? <Text type="supporting">Recent {overallStats.matchesPlayed} games</Text>
              : statsLoading ? <Skeleton className="pmc-stat-skeleton" width="var(--spacing-24)" height="var(--spacing-2)" radius="none" index={7} /> : null}
            {snapshotTime ? <Tooltip content="TFT refreshes this snapshot periodically. It does not update after every damage event." hasHoverIndication={false}><Text type="supporting" hasTabularNumbers>Updated {snapshotTime}</Text></Tooltip> : null}
          </VStack>
        </VStack> : !statsLoading && !beforeGame ? <VStack className="pmc-card__unavailable" gap={1}><Icon icon={EyeOff} color="secondary" /><Text type="supporting">Statistics unavailable</Text></VStack> : null}
        {!beforeGame && !matchStats && player.score && player.score !== '—' ? <Text hasTabularNumbers type="supporting">Match · {player.score}</Text> : null}
      </VStack>
    </Card>
  )
}

export function PlayerMatchCards({teams, onSelectPlayer, ...context}: PlayerMatchCardsProps) {
  const [activeTagId, setActiveTagId] = useState<string | null>(null)
  const [manualOrder, setManualOrder] = useState<{scope: string; teams: number[][]} | null>(null)
  const [keyboardMove, setKeyboardMove] = useState<{scope: string; team: number; player: number; original: number[][]} | null>(null)
  const [dragging, setDragging] = useState<{scope: string; team: number; player: number} | null>(null)
  const [dropTarget, setDropTarget] = useState<{scope: string; team: number; player: number} | null>(null)
  const [announcement, setAnnouncement] = useState('')
  const dragSource = useRef<typeof dragging>(null)
  const instructionsId = useId()
  const tagSelection = {activeTagId, setActiveTagId}
  const layout = resolveMatchLayout({teams, ...context})
  const canReorder = context.allowReorder === true && context.completed !== true
  const freeForAll = layout.kind === 'free-for-all'
  const duos = layout.kind === 'duos'
  const cardContext = duos ? {...context, teamMode: 'duos' as const} : context
  const inParty = Boolean(context.phase && ['lobby', 'matchmaking', 'readycheck'].includes(context.phase))
  const beforeGame = !context.completed && Boolean(context.phase && context.phase !== 'live')
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
  const scope = JSON.stringify([context.game, context.matchId, context.map, context.label, layout.kind, canReorder,
    sortedTeams.map(team => [team.name, team.players.map(player => [player.riotId, player.name, player.self])])])
  const orders = canReorder && manualOrder?.scope === scope ? manualOrder.teams : suggestedOrder
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
    setActiveTagId(null)
    setAnnouncement(`Card moved to position ${target + 1} of ${orders[team].length}.`)
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
        setActiveTagId(null)
        if (isSelected) { setKeyboardMove(null); setAnnouncement(`Card placed at position ${position + 1}.`); return }
        setKeyboardMove({scope, team, player, original: orders.map(order => [...order])})
        setAnnouncement(`Card selected at position ${position + 1}. Use arrow keys to move, Enter to place, or Escape to cancel.`)
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
        setActiveTagId(null)
        event.dataTransfer.effectAllowed = 'move'
        event.dataTransfer.setData('application/x-peaks-player-card', '1')
        const card = event.currentTarget.closest('.pmc-card')
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

  return <VStack className="pmc-lineup" gap={6}>
    {canReorder ? <VisuallyHidden id={instructionsId}>Drag to another position within {freeForAll ? 'this lobby' : 'the same team'}. With a keyboard, press Enter or Space to select a card, use arrow keys to move, then Enter or Space to place. Escape cancels the move.</VisuallyHidden> : null}
    {canReorder ? <VisuallyHidden role="status" aria-live="polite" aria-atomic="true">{announcement}</VisuallyHidden> : null}
    {sortedTeams.some(reorderableTeam) ? <HStack align="center" justify="between" gap={3}>
      <Text type="supporting">{manualOrder?.scope === scope ? freeForAll ? 'Custom order · drag within this lobby' : 'Custom order · drag within each team' : layout.canAlignRoles ? 'Matched by role · drag to arrange' : freeForAll ? 'Drag cards to arrange the lobby' : 'Drag cards to arrange each team'}</Text>
      <Button label="Reset order" icon={<Icon icon={RotateCcw} />} size="sm" variant="ghost" isDisabled={manualOrder?.scope !== scope} onClick={() => { setManualOrder(null); setKeyboardMove(null); finishDrag(); setAnnouncement('Suggested card order restored.') }} />
    </HStack> : null}
    <Grid className="pmc-teams" data-layout={layout.kind} columns={duos || sortedTeams.length > 2 ? {minWidth: 400, max: 2, repeat: 'fit'} : 1} gap={6}>
    {sortedTeams.map((team, teamIndex) => {
      const unknownPairing = duos && !isConfirmedDuo(team)
      const allied = team === ownTeam && !freeForAll
      const opposing = !unknownPairing && Boolean(ownTeam && !allied)
      const identityOffset = sortedTeams.slice(0, teamIndex).reduce((sum, item) => sum + item.players.length, 0)
      const heading = duos ? unknownPairing ? 'Players' : allied ? 'Your duo' : `Duo ${teamIndex + 1}`
        : inParty && sortedTeams.length === 1 ? 'Your party' : freeForAll ? context.game === 'Teamfight Tactics' ? 'Players' : 'Free for all' : allied ? 'Your team' : opposing ? sortedTeams.length > 2 ? team.name : 'Opponents' : team.name
      const group = <VStack className="pmc-team" gap={3} role={duos ? 'group' : undefined} aria-label={duos ? heading : undefined}>
          <HStack className="pmc-team__header" align="center" justify="between" gap={3}>
            <HStack align="center" gap={3}>
              <Heading level={2}>{heading}</Heading>
              <Text type="supporting">{team.players.length} {team.players.length === 1 ? 'player' : 'players'}{!beforeGame && team.won != null ? ` · ${team.won ? 'Victory' : 'Defeat'}` : ''}</Text>
            </HStack>
            {!beforeGame && !freeForAll && team.score != null ? <Text className="pmc-team__score" hasTabularNumbers weight="bold">{team.score}</Text> : null}
          </HStack>
          {unknownPairing ? <Text type="supporting">Pairings unavailable</Text> : null}
          <Grid className="pmc-team__cards" columns={matchGridColumns(team.players.length, context.game)} gap={3}>
            {orders[teamIndex].map((originalIndex, position) => {
              const player = team.players[originalIndex]
              return <PlayerCard key={originalIndex} player={player} index={identityOffset + originalIndex} team={team} tone={player.self ? 'self' : freeForAll ? 'ffa' : allied ? 'ally' : opposing ? 'enemy' : 'neutral'} party={player.partyId ? partyGroups.get(player.partyId) : undefined} context={cardContext} tagSelection={tagSelection} reorder={reorderableTeam(team) ? reorder(teamIndex, originalIndex, position) : undefined} onSelectPlayer={onSelectPlayer} />
            })}
          </Grid>
      </VStack>
      return <GridSpan key={`${team.name}-${teamIndex}`} columns={unknownPairing ? 'full' : 1}>{group}</GridSpan>
    })}
    </Grid>
  </VStack>
}
