import {Fragment, useId, useState, type ReactNode} from 'react'
import {ChevronDown, Clock3, Heart, Hexagon, UsersRound} from 'lucide-react'
import {displayText, formatNumber, localeTags, t, useLocale} from '../i18n'
import {statsRows, validNumber as known} from '../matchStatRows'
import type {MatchPlayer} from '../types'
import {Button, HStack, Icon, IconButton, Text, Tooltip, VisuallyHidden, VStack} from '../ui'
import {TftBoard} from '../screens/TftAccountProfile'
import {AccountRankEmblem} from './AccountRankEmblem'
import {LiveRoster, type LiveGameProps, type LiveRosterGroup} from './LiveRoster'
import './tftLiveStandings.css'

const stat = (value: number) => formatNumber(value, {maximumFractionDigits: 1})
const liveStats = (player: MatchPlayer) => player.hidden ? undefined : player.stats
const boardSize = (player: MatchPlayer) => liveStats(player)?.boardUnits ?? (player.hidden ? undefined : player.composition?.units?.length)
const standingOf = (player: MatchPlayer) => {
  const value = liveStats(player)?.standing
  return known(value) && Number.isInteger(value) && value > 0 ? value : undefined
}

function TacticianName({name}: {name: string}) {
  const tag = name.lastIndexOf('#')
  return <bdi className="tft-live-name">{tag > 0 ? <>{name.slice(0, tag)}<small>{name.slice(tag)}</small></> : name}</bdi>
}

function ScoutDetail({player}: {player: MatchPlayer}) {
  const locale = useLocale()
  const stats = liveStats(player)
  const composition = player.composition
  const metrics = [
    [t('Level'), stats?.level], [t('Gold'), stats?.gold], [t('Damage to players'), stats?.damage],
    [t('Eliminations'), stats?.playersEliminated], [t('Augments'), composition?.augments?.length ? undefined : stats?.augmentCount],
  ] as const
  const updated = known(stats?.observedAt) && stats.observedAt > 0 ? new Date(stats.observedAt * 1000) : null
  const history = player.hidden ? undefined : player.overallStats
  const recent = history ? statsRows(history).filter(row => row.overall !== '—') : []
  return <VStack className="tft-scout-body" gap={3}>
    {composition && <TftBoard compact composition={composition} label={t('Board')} />}
    <VStack className="tft-scout-stats">
      {metrics.map(([label, value]) => known(value) ? <HStack as="dl" key={label} className="tft-scout-stat" align="center" gap={3}><dt>{label}</dt><dd>{stat(value)}</dd></HStack> : null)}
      {known(player.accountLevel) && <HStack as="dl" className="tft-scout-stat" gap={3}><dt>{t('Account level')}</dt><dd>{stat(player.accountLevel)}</dd></HStack>}
      {validRank(player.peakRank) && (player.peakRankSeason || player.peakRank !== (player.currentRank || player.rank)) && <HStack as="dl" className="tft-scout-stat" align="center" gap={3}><dt>{t('Peak rating')}</dt><dd><AccountRankEmblem game="Teamfight Tactics" rank={player.peakRank} /> {displayText(player.peakRankSeason)}</dd></HStack>}
    </VStack>
    {player.statsLoading && <Text type="supporting">{t('Fetching stats')}</Text>}
    {recent.length > 0 ? <VStack gap={1}>
      <strong>{history?.matchesPlayed ? t('Recent {{count}} games', {count: history.matchesPlayed}) : t('Overall')}</strong>
      {recent.map(row => <HStack as="dl" className="tft-scout-stat" key={row.label} align="center" justify="between" gap={2}>
        <dt>{row.label === 'Placement' && history?.matchesPlayed ? t('Average placement') : t(row.label)}</dt><dd>{row.overall}</dd>
      </HStack>)}
    </VStack> : null}
    {updated && Number.isFinite(updated.getTime()) ? <Tooltip content={t('TFT refreshes this snapshot periodically. It does not update after every damage event.')}>
      <HStack className="tft-scout-time" align="center" gap={1}><Icon icon={Clock3} size="xsm" /><time dateTime={updated.toISOString()}>{updated.toLocaleTimeString(localeTags[locale], {hour: '2-digit', minute: '2-digit', second: '2-digit'})}</time></HStack>
    </Tooltip> : null}
  </VStack>
}

const validRank = (value?: string) => Boolean(value?.trim() && !/^(unknown|unavailable|rank unavailable|—|-)$/i.test(value.trim()))

function hasScoutDetail(player: MatchPlayer) {
  const s = liveStats(player)
  const board = player.composition
  return !player.hidden && Boolean(player.statsLoading || (validRank(player.peakRank) && (player.peakRankSeason || player.peakRank !== (player.currentRank || player.rank)))
    || [player.accountLevel, s?.level, s?.gold, s?.damage, s?.playersEliminated, s?.augmentCount].some(known)
    || (known(s?.observedAt) && s.observedAt > 0) || board?.units?.length || board?.augments?.length || board?.traits?.some(trait => trait.tier > 0)
    || (player.overallStats && statsRows(player.overallStats).some(row => row.overall !== '—')))
}

function Standings({groups, duos, resetOrder, hyperRoll}: {groups: LiveRosterGroup[]; duos: boolean; resetOrder: ReactNode; hyperRoll: boolean}) {
  const [selectedKey, setSelectedKey] = useState<string | null>(null)
  const detailId = useId()
  const rows = groups.flatMap(group => group.rows)
  const showRanks = rows.some(({player}) => !player.hidden && validRank(player.currentRank || player.rank))
  const columns = showRanks ? 6 : 5
  const health = rows.map(row => liveStats(row.player)?.health).filter(known)
  const scale = Math.max(hyperRoll ? 20 : 100, ...health)
  if (!rows.length) return null
  return <VStack className="tft-live">
    {resetOrder ? <HStack justify="end">{resetOrder}</HStack> : null}
    <section className="tft-live-ladder">
      <table className="tft-live-table" aria-label={t('Lobby standings')}>
        <thead><tr>
          <th className="tft-live-place" scope="col"><abbr title={t('Standing')}>#</abbr></th>
          <th scope="col"><VisuallyHidden>{t('Tactician')}</VisuallyHidden></th>
          {showRanks && <th className="tft-live-rank" scope="col"><VisuallyHidden>{t('Current rating')}</VisuallyHidden></th>}
          <th className="tft-live-health" scope="col" title={t('Health')}><Icon icon={Heart} size="sm" label={t('Health')} /></th>
          <th className="tft-live-board" scope="col" title={t('Board units')}><Icon icon={Hexagon} size="sm" label={t('Board units')} /></th>
          <th className="tft-live-handle" scope="col"><VisuallyHidden>{t('Drag to a new position, or select and use arrow keys')}</VisuallyHidden></th>
        </tr></thead>
        {groups.filter(group => group.rows.length > 0).map((group, index) => <tbody key={index}>
          {duos ? <tr className="tft-live-pair"><th colSpan={columns} scope="rowgroup"><Icon icon={UsersRound} size="sm" /> {group.team.grouping === 'unassigned' ? t('Pairings unavailable') : group.heading}</th></tr> : null}
          {group.rows.map(row => {
            const standing = standingOf(row.player)
            const hp = liveStats(row.player)?.health
            const board = boardSize(row.player)
            const scoutable = hasScoutDetail(row.player)
            const expanded = selectedKey === row.key && scoutable
            return <Fragment key={row.key}><tr {...row.rowProps} className={['tft-live-row', row.rowProps.className].filter(Boolean).join(' ')} data-selected={expanded || undefined} data-self={row.player.self || undefined} data-out={hp === 0}>
              <td className="tft-live-place" data-standing={standing}>{standing == null ? '—' : stat(standing)}</td>
              <td className="tft-live-identity">
                {row.onSelect ? <Button className="tft-live-scout" variant="ghost" label={t('Open profile for {{name}}', {name: row.name})} onClick={row.onSelect}><TacticianName name={row.name} /></Button> : <TacticianName name={row.name} />}
                {row.player.self && <small className="tft-live-identity__status">{t('You')}</small>}
                {row.party && <span className="tft-live-party" title={t('Party {{number}}', {number: row.party.number})}><Icon icon={UsersRound} size="xsm" /> {row.party.number}</span>}
              </td>
              {showRanks && <td className="tft-live-rank">{!row.player.hidden && <AccountRankEmblem game="Teamfight Tactics" rank={row.player.currentRank || row.player.rank} />}</td>}
              <td className="tft-live-health">{known(hp) ? <HStack className="tft-live-vital" gap={2} align="center">
                <strong title={hp === 0 ? t('Eliminated') : undefined}>{stat(hp)}</strong><meter aria-hidden="true" min={0} max={scale} value={hp} data-low={hp > 0 && hp <= scale / 4} />
              </HStack> : '—'}</td>
              <td className="tft-live-board">{known(board) ? stat(board) : '—'}</td>
              <td className="tft-live-handle"><HStack justify="end" align="center">{row.reorderHandle}{scoutable ? <IconButton label={t('Scout {{name}}', {name: row.name})} size="sm" variant="ghost" aria-expanded={Boolean(expanded)} aria-controls={expanded ? detailId : undefined} icon={<Icon icon={ChevronDown} size="sm" />} onClick={() => setSelectedKey(expanded ? null : row.key)} /> : null}</HStack></td>
            </tr>{expanded && <tr><td colSpan={columns} id={detailId} className="tft-live-detail"><ScoutDetail player={row.player} /></td></tr>}</Fragment>
          })}
        </tbody>)}
      </table>
    </section>
  </VStack>
}

export function TftLiveStandings({match, onSelectPlayer}: LiveGameProps) {
  useLocale()
  const hyperRoll = match.queue === '1130' || /hyper roll|tft_turbo/i.test(match.mode ?? '')
  return <LiveRoster match={match} onSelectPlayer={onSelectPlayer}>{({groups, kind, resetOrder}) =>
    <Standings key={match.id ?? match.map} groups={groups} duos={kind === 'duos'} resetOrder={resetOrder} hyperRoll={hyperRoll} />
  }</LiveRoster>
}
