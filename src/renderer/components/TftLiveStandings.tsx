import {useId, useRef, useState, type ReactNode} from 'react'
import {ArrowUpRight, ChevronRight, Clock3, Heart, Hexagon, ListOrdered, Trophy, UsersRound} from 'lucide-react'
import {gameArtwork, rankAsset} from '../assets'
import {displayText, formatNumber, localeTags, t, useLocale} from '../i18n'
import {statsRows, validNumber as known} from '../matchStatRows'
import {tftAssetLabel, tftUnitPortrait} from '../profileAssets'
import type {MatchPlayer, TftComposition} from '../types'
import {Button, Heading, HStack, Icon, Text, Tooltip, VisuallyHidden, VStack} from '../ui'
import {LiveRoster, type LiveGameProps, type LiveRosterGroup, type LiveRosterRow} from './LiveRoster'
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

function CompetitionRank({value, label}: {value?: string; label: string}) {
  const rank = value?.trim()
  if (!rank || /^(unknown|unavailable|rank unavailable)$/i.test(rank)) return null
  const image = /^(iron|bronze|silver|gold|platinum|emerald|diamond|master|grandmaster|challenger)(\s|$)/i.test(rank) ? rankAsset('Teamfight Tactics', rank) : undefined
  return <HStack as="dl" className="tft-scout-stat" align="center" justify="between" gap={2}>
    <dt>{label}</dt><dd>{image ? <img className="tft-scout-rank" src={image} alt="" /> : null}{displayText(rank)}</dd>
  </HStack>
}

function ScoutComposition({composition}: {composition: TftComposition}) {
  const traits = composition.traits?.filter(trait => trait.tier > 0)
  return <>
    {composition.units?.length ? <VStack gap={2}>
      <strong>{t('Board')}</strong>
      <HStack as="ul" className="tft-scout-units" wrap gap={1}>
        {composition.units.map((unit, index) => {
          const portrait = tftUnitPortrait(unit.id, composition.setNumber)
          const name = tftAssetLabel('champion', unit.id, composition.setNumber)
          const label = t('{{unit}}, {{stars}} stars', {unit: name, stars: unit.stars})
          return <li key={`${unit.id}-${index}`}><Tooltip content={label}>
            {portrait ? <img src={portrait} alt={label} /> : <Text type="supporting">{label}</Text>}
          </Tooltip></li>
        })}
      </HStack>
    </VStack> : null}
    {traits?.length ? <VStack gap={1}><strong>{t('Active traits')}</strong><Text type="supporting" color="secondary">{traits.map(trait => `${tftAssetLabel('trait', trait.id)} ×${trait.count}`).join(' · ')}</Text></VStack> : null}
    {composition.augments?.length ? <VStack gap={1}><strong>{t('Augments')}</strong><Text type="supporting" color="secondary">{composition.augments.map(id => tftAssetLabel('augments', id)).join(' · ')}</Text></VStack> : null}
  </>
}

function ScoutDetail({row, headingId}: {row: LiveRosterRow; headingId: string}) {
  const locale = useLocale()
  const {player} = row
  const stats = liveStats(player)
  const standing = standingOf(player)
  const board = boardSize(player)
  const metrics = [
    [t('Board units'), board], [t('Level'), stats?.level], [t('Augments'), stats?.augmentCount],
    [t('Gold'), stats?.gold], [t('Damage to players'), stats?.damage], [t('Eliminations'), stats?.playersEliminated],
  ] as const
  const updated = known(stats?.observedAt) && stats.observedAt > 0 ? new Date(stats.observedAt * 1000) : null
  const hasTelemetry = standing != null || known(stats?.health) || metrics.some(([, value]) => known(value))
  const history = player.hidden ? undefined : player.overallStats
  const recent = history ? statsRows(history).filter(row => row.overall !== '—') : []
  return <>
    <VStack className="tft-scout-identity" justify="end">
      <img className="tft-scout-arena" src={gameArtwork('Teamfight Tactics')} alt="" />
      <VStack className="tft-scout-identity__text" gap={1}>
        <Heading level={3} id={headingId} className="tft-scout-title"><TacticianName name={row.name} /></Heading>
        {player.self || (!player.hidden && known(player.accountLevel)) ? <Text type="supporting" className="tft-scout-subtitle">
          {[player.self ? t('You') : null, !player.hidden && known(player.accountLevel) ? t('Level {{level}}', {level: player.accountLevel}) : null].filter(Boolean).join(' · ')}
        </Text> : null}
      </VStack>
    </VStack>
    <VStack className="tft-scout-body" gap={4}>
      {standing != null || known(stats?.health) ? <HStack className="tft-scout-metrics">
        {standing != null ? <VStack as="dl" gap={1}><dt><Icon icon={ListOrdered} size="sm" />{t('Standing')}</dt><dd>#{stat(standing)}</dd></VStack> : null}
        {known(stats?.health) ? <VStack as="dl" gap={1}><dt><Icon icon={Heart} size="sm" />{t('Health')}</dt><dd>{stat(stats.health)}</dd></VStack> : null}
      </HStack> : null}
      <VStack className="tft-scout-stats">
        {metrics.map(([label, value]) => known(value) ? <HStack as="dl" key={label} className="tft-scout-stat" align="center" justify="between" gap={2}><dt>{label}</dt><dd>{stat(value)}</dd></HStack> : null)}
        {!player.hidden ? <>
          <CompetitionRank value={player.currentRank ?? player.rank} label={t('Current rating')} />
          <CompetitionRank value={player.peakRank} label={player.peakRankSeason ? `${t('Peak rating')} · ${displayText(player.peakRankSeason)}` : t('Peak rating')} />
        </> : null}
      </VStack>
      {!player.hidden && player.composition ? <ScoutComposition composition={player.composition} /> : null}
      {!hasTelemetry ? <Text type="supporting" color="secondary">{player.statsLoading && !player.hidden ? t('Fetching stats') : t('Statistics unavailable')}</Text> : null}
      {recent.length > 0 ? <VStack gap={1}>
        <strong>{history?.matchesPlayed ? t('Recent {{count}} games', {count: history.matchesPlayed}) : t('Overall')}</strong>
        {recent.map(row => <HStack as="dl" className="tft-scout-stat" key={row.label} align="center" justify="between" gap={2}>
          <dt>{row.label === 'Placement' && history?.matchesPlayed ? t('Average placement') : t(row.label)}</dt><dd>{row.overall}</dd>
        </HStack>)}
      </VStack> : null}
      {updated && Number.isFinite(updated.getTime()) ? <Tooltip content={t('TFT refreshes this snapshot periodically. It does not update after every damage event.')}>
        <HStack className="tft-scout-time" align="center" gap={1}><Icon icon={Clock3} size="xsm" />{t('Updated')} <time dateTime={updated.toISOString()}>{updated.toLocaleTimeString(localeTags[locale], {hour: '2-digit', minute: '2-digit', second: '2-digit'})}</time></HStack>
      </Tooltip> : null}
      {row.onSelect ? <Button variant="secondary" className="tft-scout-profile" label={t('Open profile for {{name}}', {name: row.name})} onClick={row.onSelect}>
        {t('Player profile')}<Icon icon={ArrowUpRight} size="sm" />
      </Button> : null}
    </VStack>
  </>
}

function Standings({groups, duos, resetOrder, hyperRoll}: {groups: LiveRosterGroup[]; duos: boolean; resetOrder: ReactNode; hyperRoll: boolean}) {
  const [selectedKey, setSelectedKey] = useState<string | null>(null)
  const panelRef = useRef<HTMLElement>(null)
  const detailId = useId()
  const headingId = useId()
  const rows = groups.flatMap(group => group.rows)
  const selected = rows.find(row => row.key === selectedKey) ?? rows.find(row => row.player.self) ?? rows[0]
  const health = rows.map(row => liveStats(row.player)?.health).filter(known)
  const scale = Math.max(hyperRoll ? 20 : 100, ...health)
  const scout = (key: string) => {
    setSelectedKey(key)
    const panel = panelRef.current
    if (panel && panel.getBoundingClientRect().top >= window.innerHeight) panel.focus()
  }
  if (!selected) return null
  return <VStack className="tft-live">
    <HStack className="tft-live-heading" align="center" justify="between" gap={3} wrap>
      <HStack align="center" gap={2}><Icon icon={Trophy} className="tft-live-heading__mark" size="lg" /><Heading level={2}>{t('Lobby standings')}</Heading></HStack>
      <HStack align="center" gap={2} wrap>
        {resetOrder}
        {health.length === rows.length && rows.length >= 8 ? <HStack className="tft-live-remaining" align="center" gap={1}><Icon icon={UsersRound} size="sm" />{t('{{alive}} / {{total}} alive', {alive: health.filter(value => value > 0).length, total: rows.length})}</HStack> : null}
      </HStack>
    </HStack>
    <section className="tft-live-layout" aria-label={t('Lobby standings')}>
      <section className="tft-live-ladder">
        <table className="tft-live-table" aria-label={t('Lobby standings')}>
          <thead><tr>
            <th className="tft-live-place" scope="col"><abbr title={t('Standing')}>#</abbr></th>
            <th scope="col">{t('Tactician')}</th>
            <th className="tft-live-health" scope="col">{t('Health')}</th>
            <th className="tft-live-board" scope="col">{t('Board')}</th>
            <th className="tft-live-handle" scope="col"><VisuallyHidden>{t('Drag to a new position, or select and use arrow keys')}</VisuallyHidden></th>
          </tr></thead>
          {groups.filter(group => group.rows.length > 0).map((group, index) => <tbody key={index}>
            {duos ? <tr className="tft-live-pair"><th colSpan={5} scope="rowgroup"><Icon icon={UsersRound} size="sm" /> {group.team.grouping === 'unassigned' ? t('Pairings unavailable') : group.heading}</th></tr> : null}
            {group.rows.map(row => {
              const standing = standingOf(row.player)
              const hp = liveStats(row.player)?.health
              const board = boardSize(row.player)
              return <tr key={row.key} {...row.rowProps} className={['tft-live-row', row.rowProps.className].filter(Boolean).join(' ')} data-selected={selected.key === row.key} data-out={hp === 0}>
                <td className="tft-live-place" data-standing={standing}>{standing == null ? '—' : stat(standing)}</td>
                <td className="tft-live-identity">
                  <Button className="tft-live-scout" variant="ghost" label={t('Scout {{name}}', {name: row.name})} aria-controls={detailId} aria-pressed={selected.key === row.key} onClick={() => scout(row.key)}>
                    <TacticianName name={row.name} /><Icon icon={ChevronRight} size="sm" />
                  </Button>
                  {row.player.self || hp === 0 || row.party ? <small className="tft-live-identity__status">{[row.player.self ? t('You') : null, hp === 0 ? t('Eliminated') : null, row.party ? t('Party {{number}}', {number: row.party.number}) : null].filter(Boolean).join(' · ')}</small> : null}
                </td>
                <td className="tft-live-health">{known(hp) ? <HStack className="tft-live-vital" gap={2} align="center">
                  <strong>{stat(hp)}</strong><meter aria-hidden="true" min={0} max={scale} value={hp} data-low={hp > 0 && hp <= scale / 4} />
                </HStack> : '—'}</td>
                <td className="tft-live-board">{known(board) ? <HStack gap={1} align="center" justify="center"><Icon icon={Hexagon} size="sm" />{stat(board)}</HStack> : '—'}</td>
                <td className="tft-live-handle">{row.reorderHandle}</td>
              </tr>
            })}
          </tbody>)}
        </table>
      </section>
      <aside ref={panelRef} className="tft-scout" id={detailId} tabIndex={-1} aria-labelledby={headingId}><ScoutDetail row={selected} headingId={headingId} /></aside>
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
