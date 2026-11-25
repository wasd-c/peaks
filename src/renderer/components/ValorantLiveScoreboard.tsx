import {useId, useState} from 'react'
import {ChevronDown, Crosshair, Shield, UserRound, UsersRound} from 'lucide-react'
import {hasExactValorantRankAsset, valorantAgentAsset, valorantAgentName, valorantRankAsset} from '../assets'
import {displayText, t, useLocale} from '../i18n'
import {historicalPerformanceTags, playerPerformanceTags} from '../matchAnalytics'
import {hasNumbers, statsRows} from '../matchStatRows'
import {HStack, Icon, IconButton, SegmentedControl, SegmentedControlItem, Tooltip, VStack, VisuallyHidden} from '../ui'
import {LiveRoster, type LiveGameProps, type LiveRosterRow} from './LiveRoster'
import './valorantLiveScoreboard.css'

type StatSource = 'match' | 'overall'
type StatRow = ReturnType<typeof statsRows>[number]
const metrics = [
  {label: 'ACS', help: 'Average combat score'},
  {label: 'ADR', help: 'Average damage per round'},
  {label: 'HS%', help: 'Headshot %'},
] as const
const kdaFields = ['Kills', 'Deaths', 'Assists'] as const

function RankEmblem({rank}: {rank?: string}) {
  if (!rank?.trim()) return <span className="vls-missing" aria-label={t('Rank unavailable')}>—</span>
  return hasExactValorantRankAsset(rank)
    ? <><img className="vls-rank-emblem" src={valorantRankAsset(rank)} alt={displayText(rank)} /><span aria-hidden="true" className="vls-rank-caption">{displayText(rank)}</span></>
    : <span className="vls-rank-name">{displayText(rank)}</span>
}

function PlayerBreakdown({row, stats}: {row: LiveRosterRow; stats: StatRow[]}) {
  const {player, name} = row
  const sources = [
    {label: 'Tags earned this match', tags: playerPerformanceTags(player, 'VALORANT')},
    {label: 'Tags from past games', tags: historicalPerformanceTags(player, 'VALORANT')},
  ]
  const visibleStats = stats.filter(stat => stat.match !== '—' || stat.overall !== '—')
  const rank = player.currentRank || player.rank
  return <VStack gap={4} className="vls-breakdown">
    <HStack gap={5} wrap align="center">
      {rank ? <span><strong>{t('Current')}</strong> {displayText(rank)}</span> : null}
      {player.peakRank ? <span><strong>{t('Peak')}</strong> {displayText(player.peakRank)}{player.peakRankSeason ? ` · ${player.peakRankSeason}` : ''}</span> : null}
      {player.accountLevel != null ? <span>{t('Level {{level}}', {level: player.accountLevel})}</span> : null}
      {player.role ? <span>{t('Role')} · {displayText(player.role)}</span> : null}
    </HStack>
    {visibleStats.length > 0 ? <table className="vls-compare" aria-label={t('{{name}} statistics', {name})}>
      <thead><tr><th scope="col">{t('Stats')}</th><th scope="col">{t('Match')}</th><th scope="col">{player.overallStats?.matchesPlayed ? t('Recent {{count}} games', {count: player.overallStats.matchesPlayed}) : t('Recent games')}</th></tr></thead>
      <tbody>{visibleStats.map(stat => <tr key={stat.label}><th scope="row">{t(stat.label)}</th><td>{stat.match}</td><td>{stat.overall}</td></tr>)}</tbody>
    </table> : null}
    {player.score && player.score !== '—' && !hasNumbers(player.stats) ? <span>{t('Match ·')} {player.score}</span> : null}
    {player.statsLoading && !player.hidden ? <span>{t('Fetching player statistics')}</span> : null}
    {!visibleStats.length && !player.statsLoading && !player.score ? <span>{t('Statistics unavailable')}</span> : null}
    {sources.filter(source => source.tags.length > 0).map(source => <VStack key={source.label} gap={1} className="vls-tags">
      <strong>{t(source.label)}</strong>
      {source.tags.map(tag => <p key={tag.label}><b>{tag.label}</b> {tag.detail}</p>)}
    </VStack>)}
  </VStack>
}

function PlayerRow({row, source}: {row: LiveRosterRow; source: StatSource}) {
  const {player, name, onSelect, party, rowProps, reorderHandle} = row
  const [expanded, setExpanded] = useState(false)
  const detailsId = useId()
  const portrait = valorantAgentAsset(player.agent)
  const agentName = displayText(valorantAgentName(player.agent) || 'Agent unavailable')
  const rank = player.currentRank || player.rank
  const stats = statsRows(player.overallStats, player.stats, 'VALORANT')
  const value = (label: string) => stats.find(stat => stat.label === label)?.[source] ?? '—'
  const awaitingHistory = source === 'overall' && !player.hidden && player.statsLoading
  const keyStats = kdaFields.map(value)
  const scoreKda = source === 'match' && keyStats.every(stat => stat === '—') && player.score?.match(/^\s*(\d+)\s*\/\s*(\d+)\s*\/\s*(\d+)\s*$/)
  const kda = scoreKda ? scoreKda.slice(1) : keyStats
  const separator = name.indexOf('#')
  const ign = separator > 0 ? name.slice(0, separator) : name
  const tag = separator > 0 ? name.slice(separator) : ''
  const identity = <>
    <span className="vls-portrait">{portrait ? <img src={portrait} alt="" /> : <UserRound aria-hidden />}</span>
    <span className="vls-player-copy">
      <span className="vls-name"><strong>{ign}</strong>{tag && <small>{tag}</small>}</span>
      <span className="vls-agent">{agentName}{player.self && <b>{t('You')}</b>}{party && <span className="vls-party" data-color={party.color} title={t('Party {{number}}', {number: party.number})} aria-label={t('Party {{number}}', {number: party.number})}><UsersRound aria-hidden />{party.number}</span>}</span>
    </span>
  </>
  const cellValue = (stat: string) => awaitingHistory && stat === '—'
    ? <span className="vls-loading" aria-label={t('Fetching player statistics')} />
    : stat
  return <>
    <tr {...rowProps} className="vls-row" data-self={player.self || undefined} data-expanded={expanded || undefined}>
      <th scope="row">{onSelect
        ? <button type="button" className="vls-identity" aria-label={name} title={name} onClick={onSelect}>{identity}</button>
        : <span className="vls-identity" title={name}>{identity}</span>}</th>
      <td className="vls-rank-cell"><Tooltip content={displayText(rank) || t('Rank unavailable')}><span className="vls-rank"><RankEmblem rank={rank} /></span></Tooltip></td>
      <td className="vls-kda-cell"><span className="vls-kda">{kda.map((stat, index) => <span key={kdaFields[index]}>{index > 0 && <i> / </i>}{cellValue(stat)}</span>)}</span></td>
      {metrics.map(metric => <td key={metric.label} className="vls-metric" data-metric={metric.label}>{cellValue(value(metric.label))}</td>)}
      <td className="vls-controls"><HStack justify="end" align="center">
        {reorderHandle}
        <IconButton icon={<Icon icon={ChevronDown} size="sm" />} label={t('{{name}} statistics', {name})} aria-expanded={expanded} aria-controls={expanded ? detailsId : undefined} size="sm" variant="ghost" onClick={() => setExpanded(!expanded)} />
      </HStack></td>
    </tr>
    {expanded && <tr className="vls-detail-row"><td colSpan={7} id={detailsId}><PlayerBreakdown row={row} stats={stats} /></td></tr>}
  </>
}

export function ValorantLiveScoreboard({match, onSelectPlayer}: LiveGameProps) {
  useLocale()
  const [preferred, setPreferred] = useState<StatSource>()
  const players = match.teams?.flatMap(team => team.players) ?? []
  const hasMatchStats = players.some(player => hasNumbers(player.stats) || Boolean(player.score && player.score !== '—'))
  const hasHistory = players.some(player => hasNumbers(player.overallStats) || (!player.hidden && player.statsLoading))
  const source = hasHistory ? preferred ?? (hasMatchStats ? 'match' : 'overall') : 'match'

  return <LiveRoster match={match} onSelectPlayer={onSelectPlayer}>{({groups, resetOrder}) =>
    <section className="vls" aria-label={t('Scoreboard')}>
      <HStack className="vls-toolbar" justify="between" align="center" gap={3} wrap>
        <h2>{t('Scoreboard')}</h2>
        <HStack align="center" gap={2} wrap>{resetOrder}{hasHistory && <SegmentedControl value={source} onChange={next => setPreferred(next === 'overall' ? 'overall' : 'match')} label={t('Statistics source')}>
          <SegmentedControlItem value="match" label={t('Match')} />
          <SegmentedControlItem value="overall" label={t('Recent games')} />
        </SegmentedControl>}</HStack>
      </HStack>
      <section className="vls-teams" data-multiple={groups.length > 1 || undefined}>
        {groups.map((group, index) => <section key={`${group.team.name}-${index}`} className="vls-team" data-side={group.tone}>
          <HStack className="vls-team-head" justify="between" align="center" gap={2}>
            <HStack align="center" gap={2}>
              <Icon icon={group.tone === 'ally' ? Shield : group.tone === 'enemy' ? Crosshair : UsersRound} />
              <h3>{group.heading}</h3>
            </HStack>
            <HStack align="center" gap={3}>
              {groups.length > 2 && group.team.score != null && <strong>{t('Score')} {group.team.score}</strong>}
              <span>{t('{{count}} players', {count: group.rows.length})}</span>
            </HStack>
          </HStack>
          <table className="vls-table" aria-label={group.heading}>
            <thead><tr>
              <th scope="col">{t('Player')}</th><th scope="col" className="vls-rank-cell">{t('Rank')}</th>
              <th scope="col" className="vls-kda-cell" title={kdaFields.map(key => t(key)).join(' / ')}>K/D/A</th>
              {metrics.map(metric => <th scope="col" key={metric.label} className="vls-metric" data-metric={metric.label} title={t(metric.help)}>{metric.label}</th>)}
              <th scope="col" className="vls-controls"><VisuallyHidden>{t('Actions')}</VisuallyHidden></th>
            </tr></thead>
            <tbody>{group.rows.map(row => <PlayerRow key={row.key} row={row} source={source} />)}</tbody>
          </table>
        </section>)}
      </section>
    </section>
  }</LiveRoster>
}
