import {useId, useState} from 'react'
import {ChevronDown, UserRound, UsersRound} from 'lucide-react'
import {valorantAgentAsset, valorantAgentName} from '../assets'
import {displayText, t, useLocale} from '../i18n'
import {historicalPerformanceTags, playerPerformanceTags} from '../matchAnalytics'
import {hasNumbers, statsRows} from '../matchStatRows'
import {HStack, Icon, IconButton, SegmentedControl, SegmentedControlItem, VStack, VisuallyHidden} from '../ui'
import {LiveRoster, type LiveGameProps, type LiveRosterRow} from './LiveRoster'
import {AccountRankEmblem} from './AccountRankEmblem'
import './valorantLiveScoreboard.css'

type StatSource = 'match' | 'overall'
type StatRow = ReturnType<typeof statsRows>[number]
const metrics = [
  {label: 'ACS', help: 'Average combat score'},
  {label: 'ADR', help: 'Average damage per round'},
  {label: 'HS%', help: 'Headshot %'},
] as const
const kdaFields = ['Kills', 'Deaths', 'Assists'] as const

function PlayerBreakdown({row, stats, source}: {row: LiveRosterRow; stats: StatRow[]; source: StatSource}) {
  const {player} = row
  const sources = [
    {label: 'Tags earned this match', tags: playerPerformanceTags(player, 'VALORANT')},
    {label: 'Tags from past games', tags: historicalPerformanceTags(player, 'VALORANT')},
  ]
  const visibleStats = stats.filter(stat => stat.match !== '—' || stat.overall !== '—')
  const current = player.currentRankTier ?? player.currentRank ?? player.rankTier ?? player.rank
  const peak = player.peakRankTier ?? player.peakRank
  const showPeak = peak != null && (player.peakRankSeason || peak !== current)
  return <VStack gap={4} className="vls-breakdown">
    <HStack gap={5} wrap align="center">
      {showPeak ? <span className="vls-peak"><strong>{t('Peak')}</strong> {peak !== current && <AccountRankEmblem game="VALORANT" rank={player.peakRank} tierId={player.peakRankTier} />}{player.peakRankSeason ? ` · ${player.peakRankSeason}` : ''}</span> : null}
      {player.accountLevel != null ? <span>{t('Level {{level}}', {level: player.accountLevel})}</span> : null}
      {player.role ? <span>{t('Role')} · {displayText(player.role)}</span> : null}
    </HStack>
    {(['match', 'overall'] as const).map(scope => {
      const details = visibleStats.filter(stat => stat[scope] !== '—' && (scope !== source || !['Kills', 'Deaths', 'Assists', 'ACS'].includes(stat.label)))
      if (!details.length) return null
      const label = scope === 'match' ? t('Match') : player.overallStats?.matchesPlayed ? t('Recent {{count}} games', {count: player.overallStats.matchesPlayed}) : t('Recent games')
      return <section className="vls-compare" key={scope} aria-label={label}>
        <strong>{label}</strong>
        <dl>{details.map(stat => <div key={stat.label} data-overview={scope === source ? stat.label : undefined}>
          <dt>{t(stat.label)}</dt><dd>{stat[scope]}</dd>
        </div>)}</dl>
      </section>
    })}
    {player.score && player.score !== '—' && !hasNumbers(player.stats) && (source !== 'match' || !/^\s*\d+\s*\/\s*\d+\s*\/\s*\d+\s*$/.test(player.score)) ? <span>{t('Match ·')} {player.score}</span> : null}
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
  const agentName = displayText(valorantAgentName(player.agent))
  const hasCurrentRank = Boolean(player.currentRank || player.currentRankTier != null)
  const rank = hasCurrentRank ? player.currentRank : player.rank
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
    <span className="vls-portrait" title={agentName || undefined}>{portrait ? <img src={portrait} alt={agentName} /> : <UserRound aria-hidden />}</span>
    <span className="vls-player-copy">
      <span className="vls-name"><strong>{ign}</strong>{tag && <small>{tag}</small>}</span>
      <span className="vls-agent">{!portrait && agentName}{player.self && <b>{t('You')}</b>}{party && <span className="vls-party" data-color={party.color} title={t('Party {{number}}', {number: party.number})} aria-label={t('Party {{number}}', {number: party.number})}><UsersRound aria-hidden />{party.number}</span>}</span>
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
      <td className="vls-rank-cell"><AccountRankEmblem game="VALORANT" rank={rank} tierId={hasCurrentRank ? player.currentRankTier : player.rankTier} /></td>
      <td className="vls-kda-cell"><span className="vls-kda">{kda.map((stat, index) => <span key={kdaFields[index]}>{index > 0 && <i> / </i>}{cellValue(stat)}</span>)}</span></td>
      {metrics.map(metric => <td key={metric.label} className="vls-metric" data-metric={metric.label}>{cellValue(value(metric.label))}</td>)}
      <td className="vls-controls"><HStack justify="end" align="center">
        {reorderHandle}
        <IconButton icon={<Icon icon={ChevronDown} size="sm" />} label={t('{{name}} statistics', {name})} aria-expanded={expanded} aria-controls={expanded ? detailsId : undefined} size="sm" variant="ghost" onClick={() => setExpanded(!expanded)} />
      </HStack></td>
    </tr>
    {expanded && <tr className="vls-detail-row"><td colSpan={7} id={detailsId}><PlayerBreakdown row={row} stats={stats} source={source} /></td></tr>}
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
      {resetOrder || hasHistory ? <HStack className="vls-toolbar" justify="end" align="center" gap={3} wrap>
        <HStack align="center" gap={2} wrap>{resetOrder}{hasHistory && <SegmentedControl value={source} onChange={next => setPreferred(next === 'overall' ? 'overall' : 'match')} label={t('Statistics source')}>
          <SegmentedControlItem value="match" label={t('Match')} />
          <SegmentedControlItem value="overall" label={t('Recent games')} />
        </SegmentedControl>}</HStack>
      </HStack> : null}
      <section className="vls-teams" data-multiple={groups.length > 1 || undefined}>
        {groups.map((group, index) => <section key={`${group.team.name}-${index}`} className="vls-team" data-side={group.tone}>
          <HStack className="vls-team-head" justify="between" align="center" gap={2}>
            <h3>{group.heading}</h3>
            {groups.length > 2 && group.team.score != null ? <strong title={t('Score')}>{group.team.score}</strong> : null}
          </HStack>
          <table className="vls-table" aria-label={group.heading}>
            <thead><tr>
              <th scope="col"><VisuallyHidden>{t('Player')}</VisuallyHidden></th><th scope="col" className="vls-rank-cell"><VisuallyHidden>{t('Rank')}</VisuallyHidden></th>
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
