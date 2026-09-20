import {useMemo, useState} from 'react'
import {Avatar} from '@astryxdesign/core/Avatar'
import {Button} from '@astryxdesign/core/Button'
import {EmptyState} from '@astryxdesign/core/EmptyState'
import {Grid} from '@astryxdesign/core/Grid'
import {Heading} from '@astryxdesign/core/Heading'
import {HStack} from '@astryxdesign/core/HStack'
import {Icon} from '@astryxdesign/core/Icon'
import {ProgressBar} from '@astryxdesign/core/ProgressBar'
import {Section} from '@astryxdesign/core/Section'
import {Selector} from '@astryxdesign/core/Selector'
import {Tab, TabList} from '@astryxdesign/core/TabList'
import {Table, proportional} from '@astryxdesign/core/Table'
import {Text} from '@astryxdesign/core/Text'
import {Token} from '@astryxdesign/core/Token'
import {Tooltip} from '@astryxdesign/core/Tooltip'
import {VStack} from '@astryxdesign/core/VStack'
import {ArrowUpRight} from 'lucide-react'
import {aggregateProfile, filterProfileMatches, profileAgent, profileBreakdown, profileMatches, profileMode, type ProfileFilters} from '../accountProfile'
import {valorantAgentAsset, valorantMapName} from '../assets'
import {HitAccuracy} from '../components/HitAccuracy'
import {displayText, formatNumber, t, useLocale} from '../i18n'
import type {Account, Match} from '../types'
import {resultColor} from './shared'

type AccountSection = 'overview' | 'matches' | 'agents' | 'maps' | 'weapons' | 'roles'
const sections: Array<{value: AccountSection; label: string}> = [
  {value: 'overview', label: 'Overview'}, {value: 'matches', label: 'Matches'},
  {value: 'agents', label: 'Agents'}, {value: 'maps', label: 'Maps'},
  {value: 'weapons', label: 'Weapons'}, {value: 'roles', label: 'Roles'},
]
const number = (value?: number, digits = 1) => value == null ? '—' : formatNumber(value, {maximumFractionDigits: digits})
const percent = (value?: number) => value == null ? '—' : `${number(value)}%`
const evidence = (count: number) => t('{{count}} matches', {count})

export function ProfileMetric({label, value, detail, prominent = false}: {label: string; value: string; detail?: string; prominent?: boolean}) {
  return <VStack gap={1} padding={4}>
    <Tooltip content={detail} isEnabled={Boolean(detail)}><Text color="secondary" type="supporting">{label}</Text></Tooltip>
    <Text className={prominent ? 'pd-profile-metric' : undefined} weight="semibold" hasTabularNumbers>{value}</Text>
    {prominent && detail ? <Text type="supporting" color="secondary">{detail}</Text> : null}
  </VStack>
}

function Breakdown({matches, riotId, by, limit}: {matches: Match[]; riotId: string; by: 'agent' | 'map' | 'role'; limit?: number}) {
  const rows = profileBreakdown(matches, riotId, by).slice(0, limit)
  return <Table aria-label={t(by === 'agent' ? 'Agent performance' : by === 'map' ? 'Map performance' : 'Role performance')}
    data={rows} idKey="label" density="compact" columns={[
      {key: 'label', header: t(by === 'agent' ? 'Agent' : by === 'map' ? 'Map' : 'Role'), width: proportional(2), renderCell: row => <HStack gap={2} align="center">
        {by === 'agent' ? <Avatar src={valorantAgentAsset(row.label)} name={row.label} size="sm" shape="rounded" tooltip={false} /> : null}
        <Text weight="semibold">{displayText(row.label)}</Text>
      </HStack>},
      {key: 'matches', header: t('Matches'), width: proportional(1)},
      {key: 'winRate', header: t('Win rate'), width: proportional(1), renderCell: row => percent(row.winRate)},
      {key: 'kd', header: 'K/D', width: proportional(1), renderCell: row => number(row.kd, 2)},
      {key: 'adr', header: 'ADR', width: proportional(1), renderCell: row => number(row.adr)},
      {key: 'acs', header: 'ACS', width: proportional(1), renderCell: row => number(row.acs)},
      {key: 'damageDelta', header: t('DDA / round'), width: proportional(1), renderCell: row => number(row.damageDelta)},
    ]} />
}

function History({matches, riotId, onSelect}: {matches: Match[]; riotId: string; onSelect: (match: Match) => void}) {
  const rows = matches.map((match, index) => ({...aggregateProfile([match], riotId), id: match.id ?? String(index), match}))
  return <Table aria-label={t('VALORANT match history')} data={rows} idKey="id" density="balanced" hasHover columns={[
    {key: 'match', header: t('Match'), width: proportional(2), renderCell: row => <HStack gap={2} align="center">
      <Avatar name={profileAgent(row.match, riotId)} src={valorantAgentAsset(profileAgent(row.match, riotId))} size="md" shape="rounded" tooltip={false} />
      <VStack gap={0}>
        <Button label={valorantMapName(row.match.map)} size="sm" variant="ghost" onClick={() => onSelect(row.match)} />
        <Text type="supporting" color="secondary">{displayText(row.match.playedAt)} · {displayText(row.match.mode)}</Text>
      </VStack>
    </HStack>},
    {key: 'wins', header: t('Result'), width: proportional(1), renderCell: row => <VStack gap={1} align="start">
      <Token label={displayText(row.match.result)} color={resultColor(row.match.result)} size="sm" />
      <Text hasTabularNumbers>{row.match.score ?? '—'}</Text>
    </VStack>},
    {key: 'kills', header: 'K / D / A', width: proportional(1), renderCell: row => `${number(row.kills, 0)} / ${number(row.deaths, 0)} / ${number(row.assists, 0)}`},
    {key: 'kd', header: 'K/D', width: proportional(1), renderCell: row => number(row.kd, 2)},
    {key: 'acs', header: 'ACS', width: proportional(1), renderCell: row => number(row.acs)},
    {key: 'adr', header: 'ADR', width: proportional(1), renderCell: row => number(row.adr)},
    {key: 'headshotRate', header: 'HS%', width: proportional(1), renderCell: row => percent(row.headshotRate)},
    {key: 'damageDelta', header: t('DDA / round'), width: proportional(1), renderCell: row => number(row.damageDelta)},
    {key: 'kast', header: 'KAST', width: proportional(1), renderCell: row => percent(row.kast)},
  ]} />
}

export function ValorantAccountProfile({account, isSynchronizing = false, onSelectMatch}: {
  account: Account
  isSynchronizing?: boolean
  onSelectMatch: (match: Match) => void
}) {
  useLocale()
  const [section, setSection] = useState<AccountSection>('overview')
  const [filters, setFilters] = useState<ProfileFilters>({mode: 'competitive', season: 'all', agent: 'all', map: 'all'})
  const all = useMemo(() => profileMatches(account.matches ?? []), [account.matches])
  const matches = useMemo(() => filterProfileMatches(all, account.riotId, filters), [all, account.riotId, filters])
  const stats = useMemo(() => aggregateProfile(matches, account.riotId), [matches, account.riotId])
  const selectFilter = (key: keyof ProfileFilters, value: string) => setFilters(previous => ({...previous, [key]: value}))
  const options = (values: string[], label: string) => [{value: 'all', label: t(label)}, ...[...new Set(values)].sort().map(value => ({value, label: displayText(value)}))]
  const weapons = <VStack gap={3}>
    <Text color="secondary" type="supporting">{t('Kills by weapon · {{count}} matches', {count: stats.weaponMatches})}</Text>
    <Table aria-label={t('Weapon performance')} data={stats.weapons} idKey="label" density="compact" columns={[
      {key: 'label', header: t('Weapon'), width: proportional(2)},
      {key: 'kills', header: t('Kills'), width: proportional(1)},
      {key: 'share', header: t('Kill share'), width: proportional(2), renderCell: row => <ProgressBar label={row.label} isLabelHidden hasValueLabel value={row.share} variant="neutral" />},
    ]} />
  </VStack>

  return <VStack gap={6}>
      <TabList value={section} onChange={value => setSection(value as AccountSection)} hasDivider role="tablist" aria-label={t('Account statistics')}>
        {sections.map(item => <Tab key={item.value} value={item.value} label={t(item.label)} panelId={`profile-${item.value}`} />)}
      </TabList>
      <Grid className="pd-profile-filters" gap={3}>
        <Selector label={t('Game mode')} value={filters.mode} onChange={value => selectFilter('mode', value)} options={options(['competitive', ...all.map(profileMode)], 'All modes')} />
        <Selector label={t('Act')} value={filters.season} onChange={value => selectFilter('season', value)} options={options([...(account.valorantAct ? [account.valorantAct] : []), ...all.flatMap(match => match.season ? [match.season] : [])], 'All acts')} />
        <Selector label={t('Agent')} value={filters.agent} onChange={value => selectFilter('agent', value)} options={options(all.map(match => profileAgent(match, account.riotId)), 'All agents')} />
        <Selector label={t('Map')} value={filters.map} onChange={value => selectFilter('map', value)} options={options(all.map(match => valorantMapName(match.map)), 'All maps')} />
      </Grid>
      <Text color="secondary" type="supporting" role="status">{t('Detailed statistics · {{detailed}} / {{count}} matches', {detailed: stats.detailed, count: stats.matches})}</Text>
      {isSynchronizing ? <ProgressBar label={t('Synchronizing match details…')} isIndeterminate variant="neutral" />
        : matches.some(match => match.enrichmentPending) ? <Text type="supporting" color="secondary">{t('Some match details are unavailable. Refresh to retry.')}</Text> : null}

      <VStack gap={6} role="tabpanel" id={`profile-${section}`} aria-label={t(sections.find(item => item.value === section)!.label)}>
        {!matches.length ? <EmptyState title={t('No matches in this selection')} description={t('Refresh with VALORANT running, or select another mode or act.')}
          actions={<Button label={t('Clear filters')} onClick={() => setFilters({mode: 'all', season: 'all', agent: 'all', map: 'all'})} />} /> : <>
          {section === 'overview' ? <>
            <Section padding={0} variant="muted">
              <Grid columns={4}>
                <ProfileMetric prominent label={t('Damage / round')} value={number(stats.adr)} detail={evidence(stats.coverage.adr)} />
                <ProfileMetric prominent label="K/D" value={number(stats.kd, 2)} detail={evidence(stats.detailed)} />
                <ProfileMetric prominent label={t('Headshot %')} value={percent(stats.headshotRate)} detail={evidence(stats.coverage.shots)} />
                <ProfileMetric prominent label={t('Win rate')} value={percent(stats.winRate)} detail={t('{{wins}} W · {{losses}} L · {{draws}} D', stats)} />
              </Grid>
            </Section>
            <Grid className="pd-profile-metrics" gap={2}>
              <ProfileMetric label="ACS" value={number(stats.acs)} detail={evidence(stats.coverage.acs)} />
              <ProfileMetric label="KAST" value={percent(stats.kast)} detail={t('Rounds with a kill, assist, survival or a trade within 5 seconds. {{coverage}}', {coverage: evidence(stats.coverage.kast)})} />
              <ProfileMetric label={t('DDA / round')} value={number(stats.damageDelta)} detail={evidence(stats.coverage.damageDelta)} />
              <ProfileMetric label={t('Round win %')} value={percent(stats.roundWinRate)} detail={evidence(stats.coverage.rounds)} />
              <ProfileMetric label={t('Kills')} value={number(stats.kills, 0)} detail={evidence(stats.detailed)} />
              <ProfileMetric label={t('Deaths')} value={number(stats.deaths, 0)} detail={evidence(stats.detailed)} />
              <ProfileMetric label={t('Assists')} value={number(stats.assists, 0)} detail={evidence(stats.detailed)} />
              <ProfileMetric label="(K + A) / D" value={number(stats.kad, 2)} />
              <ProfileMetric label={t('Kills / round')} value={number(stats.killsPerRound, 2)} />
              <ProfileMetric label={t('First kills')} value={number(stats.firstKills, 0)} detail={evidence(stats.coverage.firstKills)} />
              <ProfileMetric label={t('First deaths')} value={number(stats.firstDeaths, 0)} detail={evidence(stats.coverage.firstDeaths)} />
              <ProfileMetric label={t('Flawless rounds')} value={number(stats.flawless, 0)} detail={evidence(stats.coverage.flawless)} />
              <ProfileMetric label={t('Aces')} value={number(stats.aces, 0)} detail={evidence(stats.coverage.aces)} />
              <ProfileMetric label={t('Playtime')} value={stats.seconds != null ? `${number(stats.seconds / 3600)} h` : '—'} detail={evidence(stats.coverage.duration)} />
            </Grid>
            <HitAccuracy head={stats.headshots} body={stats.bodyshots} legs={stats.legshots} />
            <VStack gap={3}><Heading level={3}>{t('Top agents')}</Heading><Breakdown matches={matches} riotId={account.riotId} by="agent" limit={3} /></VStack>
            <HStack justify="between" align="center"><Heading level={3}>{t('Recent matches')}</Heading><Button label={t('All matches')} icon={<Icon icon={ArrowUpRight} />} onClick={() => setSection('matches')} variant="ghost" size="sm" /></HStack>
            <History matches={matches.slice(0, 5)} riotId={account.riotId} onSelect={onSelectMatch} />
          </> : null}
          {section === 'matches' ? <History matches={matches} riotId={account.riotId} onSelect={onSelectMatch} /> : null}
          {section === 'agents' || section === 'maps' || section === 'roles' ? <Breakdown matches={matches} riotId={account.riotId} by={section === 'agents' ? 'agent' : section === 'maps' ? 'map' : 'role'} /> : null}
          {section === 'weapons' ? weapons : null}
        </>}
      </VStack>
  </VStack>
}
