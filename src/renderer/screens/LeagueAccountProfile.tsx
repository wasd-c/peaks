import {useState} from 'react'
import {Avatar} from '@astryxdesign/core/Avatar'
import {Button} from '@astryxdesign/core/Button'
import {Collapsible} from '@astryxdesign/core/Collapsible'
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
import {VStack} from '@astryxdesign/core/VStack'
import {ArrowUpRight} from 'lucide-react'
import {profileMatches, profilePlayer} from '../accountProfile'
import {displayText, formatNumber, t, useLocale} from '../i18n'
import {championBreakdown, championForMatch, gameMode, leagueSummary} from '../riotProfile'
import type {Account, Match} from '../types'
import {resultColor} from './shared'
import {ProfileMetric} from './ValorantAccountProfile'

const number = (value?: number, digits = 1) => value == null ? '—' : formatNumber(value, {maximumFractionDigits: digits})
const percent = (value?: number) => value == null ? '—' : `${number(value)}%`

export function LeagueAccountProfile({account, isSynchronizing, onSelectMatch}: {account: Account; isSynchronizing: boolean; onSelectMatch: (match: Match) => void}) {
  useLocale()
  const [section, setSection] = useState('overview')
  const [mode, setMode] = useState('all')
  const [champion, setChampion] = useState('all')
  const all = profileMatches(account.matches ?? [], 'League of Legends')
  const matches = all.filter(match => (mode === 'all' || gameMode(match) === mode) && (champion === 'all' || championForMatch(match, account.riotId)?.characterId === champion))
  const stats = leagueSummary(matches, account.riotId)
  const champions = championBreakdown(matches, account.riotId)
  const history = (rows: Match[]) => <Table aria-label={t('League match history')} density="balanced" data={rows.map((match, index) => ({id: match.id ?? String(index), match, champion: championForMatch(match, account.riotId), player: profilePlayer(match, account.riotId)}))} idKey="id" columns={[
    {key: 'champion', header: t('Champion'), width: proportional(2), renderCell: row => <HStack gap={3} align="center">
      <Avatar src={row.champion?.image} name={row.champion?.name ?? '?'} size="md" shape="rounded" tooltip={false} />
      <VStack gap={1} align="start"><Text weight="semibold">{row.champion?.name ?? t('Champion')}</Text>
        <Text type="supporting" color="secondary">{displayText(row.match.playedAt)} · {displayText(gameMode(row.match))}</Text>
        <Button label={t('View match')} aria-label={t('View match: {{name}} · {{playedAt}} · {{result}}', {name: row.champion?.name ?? t('Champion'), playedAt: displayText(row.match.playedAt), result: displayText(row.match.result)})} variant="ghost" size="sm" onClick={() => onSelectMatch(row.match)} />
      </VStack>
    </HStack>},
    {key: 'result', header: t('Result'), width: proportional(1), renderCell: row => <Token label={displayText(row.match.result)} color={resultColor(row.match.result)} size="sm" />},
    {key: 'kda', header: 'K / D / A', width: proportional(1), renderCell: row => [row.player?.stats?.kills, row.player?.stats?.deaths, row.player?.stats?.assists].map(value => number(value, 0)).join(' / ')},
    {key: 'minions', header: 'CS', width: proportional(1), renderCell: row => number(row.player?.stats?.minions, 0)},
    {key: 'damage', header: t('Damage'), width: proportional(1), renderCell: row => number(row.player?.stats?.damage, 0)},
    {key: 'vision', header: t('Vision score'), width: proportional(1), renderCell: row => number(row.player?.stats?.vision, 0)},
    {key: 'duration', header: t('Duration'), width: proportional(1), renderCell: row => row.match.durationSeconds ? `${number(row.match.durationSeconds / 60, 0)} min` : row.match.duration ?? '—'},
  ]} />
  const championTable = <Table aria-label={t('Champion performance')} density="balanced" data={champions} idKey="id" columns={[
    {key: 'champion', header: t('Champion'), width: proportional(2), renderCell: row => <HStack gap={3} align="center"><Avatar name={row.champion.name} src={row.champion.image} size="sm" tooltip={false} shape="rounded" /><Text weight="semibold">{row.champion.name}</Text></HStack>},
    {key: 'matches', header: t('Matches'), width: proportional(1)},
    {key: 'winRate', header: t('Win rate'), width: proportional(1), renderCell: row => percent(row.winRate)},
    {key: 'kda', header: 'KDA', width: proportional(1), renderCell: row => number(row.kda, 2)},
    {key: 'csPerMinute', header: 'CS / min', width: proportional(1), renderCell: row => number(row.csPerMinute)},
    {key: 'damagePerMinute', header: t('Damage / min'), width: proportional(1), renderCell: row => number(row.damagePerMinute, 0)},
  ]} />
  return <VStack gap={5}>
    <TabList value={section} onChange={setSection} hasDivider role="tablist" aria-label={t('League statistics')}>
      {[['overview', 'Overview'], ['matches', 'Matches'], ['champions', 'Champions']].map(([value, label]) => <Tab key={value} value={value} label={t(label)} panelId={`league-${value}`} />)}
    </TabList>
    <Grid className="pd-profile-filters" gap={3}>
      <Selector label={t('Game mode')} value={mode} onChange={setMode} options={[{value: 'all', label: t('All modes')}, ...[...new Set(all.map(gameMode))].map(value => ({value, label: displayText(value)}))]} />
      <Selector label={t('Champion')} value={champion} onChange={setChampion} options={[{value: 'all', label: t('All champions')}, ...championBreakdown(all, account.riotId).map(row => ({value: row.id, label: row.champion.name}))]} />
    </Grid>
    <VStack gap={1}>
      <Text type="supporting" color="secondary" role="status">{t('Detailed statistics · {{detailed}} / {{count}} matches', {detailed: stats.detailed, count: stats.matches})}</Text>
      {matches.length ? <Text type="supporting" color="secondary">{t('Each metric uses the available match details. — means unavailable.')}</Text> : null}
    </VStack>
    {isSynchronizing ? <ProgressBar label={t('Synchronizing match details…')} isIndeterminate /> : null}
    {!matches.length ? <EmptyState title={t('No matches in this selection')} description={t('Open the League client with this Riot account and refresh. Cached matches remain available after closing the game.')}
      actions={<Button label={t('Clear filters')} variant="ghost" onClick={() => {setMode('all'); setChampion('all')}} />} />
      : <VStack gap={5} role="tabpanel" id={`league-${section}`} aria-label={t(section === 'overview' ? 'Overview' : section === 'matches' ? 'Matches' : 'Champions')}>
        {section === 'overview' ? <>
          <Section padding={0} variant="muted"><Grid className="pd-profile-kpis">
            <ProfileMetric prominent label={t('Win rate')} value={percent(stats.winRate)} detail={t('{{wins}} W · {{losses}} L', stats)} />
            <ProfileMetric prominent label="KDA" value={number(stats.kda, 2)} detail="(K + A) / D" />
            <ProfileMetric prominent label="CS / min" value={number(stats.csPerMinute)} help={t('Minions and monsters killed per minute.')} />
            <ProfileMetric prominent label={t('Kill participation')} value={percent(stats.killParticipation)} />
          </Grid></Section>
          <VStack gap={3}>
            <HStack justify="between" align="center" gap={3} wrap="wrap"><Heading level={3}>{t('Recent matches')}</Heading><Button label={t('All matches')} icon={<Icon icon={ArrowUpRight} />} onClick={() => setSection('matches')} variant="ghost" size="sm" /></HStack>
            {history(matches.slice(0, 5))}
          </VStack>
          <Collapsible defaultIsOpen={false} trigger={<Text weight="semibold">{t('Advanced statistics')}</Text>}>
            <VStack paddingBlockStart={3}>
              <Grid className="pd-profile-metrics">
                <ProfileMetric label={t('Damage / min')} value={number(stats.damagePerMinute, 0)} />
                <ProfileMetric label={t('Average damage')} value={number(stats.damage, 0)} />
                <ProfileMetric label={t('Average gold')} value={number(stats.gold, 0)} />
                <ProfileMetric label={t('Vision score')} value={number(stats.vision)} />
                <ProfileMetric label={t('Kills')} value={number(stats.kills, 0)} />
                <ProfileMetric label={t('Deaths')} value={number(stats.deaths, 0)} />
                <ProfileMetric label={t('Assists')} value={number(stats.assists, 0)} />
              </Grid>
            </VStack>
          </Collapsible>
          <VStack gap={3}><Heading level={3}>{t('Top champions')}</Heading>{championTable}</VStack>
        </> : section === 'champions' ? championTable : history(matches)}
      </VStack>}
  </VStack>
}
