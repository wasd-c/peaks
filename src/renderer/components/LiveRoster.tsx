import type {HTMLAttributes, ReactNode} from 'react'
import {displayText, t, useLocale} from '../i18n'
import {isConfirmedDuo, type MatchLayout} from '../matchLayout'
import {matchPlayerProfile} from '../playerProfiles'
import type {CurrentMatch, MatchPlayer, MatchTeam, Player} from '../types'
import {usePlayerPrivacy} from './PlayerPrivacy'
import {ReorderHandle, useMatchRoster} from './useMatchRoster'

export interface LiveGameProps {
  match: CurrentMatch
  onSelectPlayer: (player: Player) => void
}

export interface LiveRosterRow {
  key: string
  player: MatchPlayer
  name: string
  onSelect?: () => void
  party?: {color: string; number: number}
  rowProps: HTMLAttributes<HTMLElement> & {
    'data-roster-row': true
    'data-dragging'?: boolean
    'data-drop-target'?: boolean
  }
  reorderHandle: ReactNode
}

export interface LiveRosterGroup {
  team: MatchTeam
  heading: string
  tone: 'ally' | 'enemy' | 'neutral'
  rows: LiveRosterRow[]
}

interface LiveRosterView {
  groups: LiveRosterGroup[]
  kind: MatchLayout['kind']
  resetOrder: ReactNode
}

export function LiveRoster({match, onSelectPlayer, children}: LiveGameProps & {
  children: (view: LiveRosterView) => ReactNode
}) {
  useLocale()
  const {displayName} = usePlayerPrivacy()
  const roster = useMatchRoster({
    ...match, teams: match.teams ?? [], phase: 'live', queueId: match.queue,
    matchId: match.id, allowReorder: !match.isStale,
  })
  const groups = roster.sortedTeams.map((team, teamIndex): LiveRosterGroup => {
    const offset = roster.sortedTeams.slice(0, teamIndex).reduce((total, group) => total + group.players.length, 0)
    const unpaired = roster.duos && !isConfirmedDuo(team)
    const neutral = roster.freeForAll || unpaired || !roster.ownTeam
    const tone = neutral ? 'neutral' : team === roster.ownTeam ? 'ally' : 'enemy'
    const heading = roster.duos ? unpaired ? t('Players') : tone === 'ally' ? t('Your duo') : displayText(team.name)
      : tone === 'ally' ? t('Your team') : tone === 'enemy' && roster.sortedTeams.length === 2 ? t('Opponents') : displayText(team.name)
    // The source may deliver the same lobby in a different order on the next
    // snapshot. Keep an open player detail attached to that identity.
    const seen = new Map<string, number>()
    const keys = team.players.map(player => {
      const id = player.riotId ?? player.name
      const occurrence = seen.get(id) ?? 0
      seen.set(id, occurrence + 1)
      return JSON.stringify([team.name, id, occurrence])
    })
    const rows = roster.orders[teamIndex].map((originalIndex, position): LiveRosterRow => {
      const player = team.players[originalIndex]
      const name = player.hidden ? t('Hidden player {{number}}', {number: offset + originalIndex + 1}) : displayName(player.riotId ?? player.name)
      const profile = match.game && matchPlayerProfile(player, {game: match.game, map: match.map, matchId: match.id, team: team.name, label: t('In game'), result: 'Live'})
      const move = roster.reorderableTeam(team) ? roster.reorder(teamIndex, originalIndex, position) : undefined
      return {
        key: keys[originalIndex],
        player, name,
        onSelect: profile ? () => onSelectPlayer(profile) : undefined,
        party: player.partyId ? roster.partyGroups.get(player.partyId) : undefined,
        rowProps: {
          'data-roster-row': true,
          'data-dragging': move?.dragging || move?.selected || undefined,
          'data-drop-target': move?.dropTarget || undefined,
          onDragEnter: move?.onDragEnter, onDragOver: move?.onDragOver, onDrop: move?.onDrop,
        },
        reorderHandle: move ? <ReorderHandle name={name} reorder={move} /> : null,
      }
    })
    return {team, heading, tone, rows}
  })
  return <>{roster.instructions}{children({groups, kind: roster.layout.kind, resetOrder: roster.resetOrder})}</>
}
