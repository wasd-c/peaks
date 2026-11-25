import {displayText, localeTags, t, useLocale} from '../i18n'
import {useId, useState, type Dispatch, type SetStateAction} from 'react'
import {Button, Card, Grid, GridSpan, Heading, HStack, Icon, Skeleton, Text, Token, Tooltip, VStack, VisuallyHidden} from '../ui'
import {ArrowUpRight, Check, Crown, EyeOff, Shield, UsersRound} from 'lucide-react'
import {hasExactValorantRankAsset, rankAsset, valorantAgentName, valorantAgentPortraitAsset} from '../assets'
import {historicalPerformanceTags, playerPerformanceTags, type PerformanceTag} from '../matchAnalytics'
import {ReorderHandle, useMatchRoster, type CardReorder} from './useMatchRoster'
import {fitsValorantRoster, isConfirmedDuo, matchGridColumns} from '../matchLayout'
import {matchPlayerProfile} from '../playerProfiles'
import type {Game, MatchPlayer, MatchTeam, Player, SessionPhase} from '../types'
import {average, hasNumbers, numeric, statsRows, validNumber} from '../matchStatRows'
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
  fitToHeight?: boolean
  onSelectPlayer: (player: Player) => void
}

function StatValue({value, loading = false, index = 0}: {value: string; loading?: boolean; index?: number}) {
  useLocale()
  if (loading && value === '—') return (
    <HStack className="pmc-stat-placeholder" role="cell" aria-label={t("Loading")} justify="end" align="center">
      <Skeleton className="pmc-stat-skeleton" width={`var(--spacing-${[7, 6, 8, 5][index % 4]})`} height="var(--spacing-2)" radius="none" index={index} />
    </HStack>
  )
  return <Text className="pmc-stat-value" role="cell" hasTabularNumbers weight="medium">{value}</Text>
}

function CardRank({game, rank, caption, compact}: {game?: Game; rank?: string; caption: string; compact?: boolean}) {
  useLocale()
  const label = rank?.trim() || 'Unavailable'
  const tier = label.toLowerCase().split(' ')[0]
  const knownRank = game === 'VALORANT' ? hasExactValorantRankAsset(rank)
    : ['iron', 'bronze', 'silver', 'gold', 'platinum', 'emerald', 'diamond', 'master', 'grandmaster', 'challenger'].includes(tier)
  const asset = game && rank && knownRank ? rankAsset(game, label) : undefined
  return (
    <HStack className={`pmc-rank${compact ? ' pmc-rank--compact' : ''}`} align="center" gap={1}>
      {asset ? <img className="pmc-rank__image" alt={t("{{label}} rank emblem", {label: displayText(label)})} src={asset} /> : <HStack className="pmc-rank__placeholder" align="center" justify="center"><Icon icon={Shield} color="secondary" /></HStack>}
      <VStack className="pmc-rank__labels" align={compact ? 'start' : 'center'} gap={1}>
        <Text className="pmc-rank__name" maxLines={1} type="supporting">{displayText(label)}</Text>
        <Text className="pmc-rank__caption" type="supporting">{displayText(caption)}</Text>
      </VStack>
    </HStack>
  )
}

interface TagSelection {
  activeTagId: string | null
  setActiveTagId: Dispatch<SetStateAction<string | null>>
}

function TagExplanation({tag, source, activeTagId, setActiveTagId}: {tag: PerformanceTag; source: 'past' | 'match'} & TagSelection) {
  useLocale()
  const tagId = useId()
  return <Tooltip
    content={`${source === 'past' ? t('Past games') : t('This match')} · ${tag.detail}`}
    hasHoverIndication={false}
    isOpen={activeTagId === tagId}
    onOpenChange={open => setActiveTagId(current => open ? tagId : current === tagId ? null : current)}>
    <Token className={`pmc-tag pmc-tag--${source}`} description={tag.detail} label={tag.label} onClick={() => setActiveTagId(current => current === tagId ? null : tagId)} size="sm" />
  </Tooltip>
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
  const language = useLocale()
  const {displayName} = usePlayerPrivacy()
  const statsStatusId = useId()
  const beforeGame = !context.completed && Boolean(context.phase && context.phase !== 'live')
  const inParty = Boolean(context.phase && ['lobby', 'matchmaking', 'readycheck'].includes(context.phase))
  const statsLoading = player.statsLoading === true && !player.hidden
  const name = player.hidden ? t('Hidden player {{number}}', {number: index + 1}) : displayName(player.riotId ?? player.name)
  const profilePlayer = beforeGame ? {...player, stats: undefined, score: undefined} : player
  const profile = context.game ? matchPlayerProfile(profilePlayer, {...context, game: context.game, team: team.name}) : null
  const portrait = context.game === 'VALORANT' ? valorantAgentPortraitAsset(player.agent) : undefined
  const rosterCard = context.game === 'League of Legends' || context.game === 'Teamfight Tactics'
  const agent = context.game === 'VALORANT' ? valorantAgentName(player.agent) : player.agent
  const character = agent || (context.game === 'Teamfight Tactics' || inParty ? undefined
    : context.game === 'League of Legends' ? beforeGame ? 'Choosing champion' : 'Champion unavailable'
      : beforeGame ? 'Choosing agent' : 'Agent unavailable')
  const identityDetails = [displayText(character), player.accountLevel != null ? t('Level {{level}}', {level: player.accountLevel}) : undefined].filter(Boolean)
  const role = player.role ? ({top: 'Top', jungle: 'Jungle', middle: 'Mid', mid: 'Mid', bottom: 'Bot', utility: 'Support', support: 'Support'}[player.role.toLowerCase()] ?? player.role) : undefined
  const matchStats = !beforeGame && hasNumbers(player.stats) ? player.stats : undefined
  const overallStats = hasNumbers(player.overallStats) ? player.overallStats : undefined
  const rows = statsRows(overallStats, matchStats, statsLoading || (context.game === 'VALORANT' && Boolean(overallStats || matchStats)) ? context.game : undefined)
    .filter(row => !context.fitToHeight || ['K/D', 'ACS', 'ADR', 'HS%'].includes(row.label))
  const kda = (['kills', 'deaths', 'assists'] as const).map(key => matchStats ? numeric(matchStats[key]) : average(overallStats?.[key], overallStats?.matchesPlayed)).join(' / ')
  const pastTags = context.game ? historicalPerformanceTags(player, context.game) : []
  const matchTags = !beforeGame && context.game ? playerPerformanceTags(player, context.game) : []
  const source = overallStats?.matchesPlayed
    ? t('Recent {{count}} games · kills, deaths, and assists averaged per game', {count: overallStats.matchesPlayed})
    : statsLoading ? t('Fetching player statistics') : t('Overall statistics are unavailable')
  const partner = tone === 'ally' && context.teamMode === 'duos'
  const snapshotTime = !context.completed && context.game === 'Teamfight Tactics' && validNumber(matchStats?.observedAt)
    ? new Date(matchStats.observedAt * 1000).toLocaleTimeString(localeTags[language], {hour: '2-digit', minute: '2-digit', second: '2-digit'}) : undefined

  return (
    <Card className={`pmc-card pmc-card--${tone}${rosterCard ? ' pmc-card--roster' : ''}`} data-party={party?.color} data-dragging={reorder?.dragging || reorder?.selected ? 'true' : undefined} data-drop-target={reorder?.dropTarget ? 'true' : undefined} onDragEnter={reorder?.onDragEnter} onDragOver={reorder?.onDragOver} onDrop={reorder?.onDrop} padding={0} role="group" aria-busy={statsLoading} aria-describedby={statsLoading ? statsStatusId : undefined} aria-label={[name, t(tone === 'self' ? 'You' : tone === 'ally' ? 'Ally' : tone === 'enemy' ? 'Opponent' : 'Player'), party ? t('Party {{number}}', {number: party.number}) : ''].filter(Boolean).join(', ')}>
      {portrait ? <img className="pmc-card__portrait" src={portrait} alt="" aria-hidden="true" /> : null}
      <VStack className="pmc-card__content" gap={4} padding={4}>
        <VStack className="pmc-card__identity" gap={1}>
          <HStack className="pmc-card__controls" align="center" justify="between" gap={2}>
            <Text className="pmc-card__side" type="supporting">{player.self ? t("YOU") : player.hidden ? t("PRIVATE PLAYER") : partner ? t("PARTNER") : tone === 'ally' ? t("ALLY") : tone === 'enemy' ? t("OPPONENT") : t("PLAYER")}</Text>
            <HStack align="center" gap={1}>
              {party ? <Tooltip content={t("Party {{number}} · players with this top border are grouped", {number: party.number})} hasHoverIndication={false}><HStack className="pmc-card__party" align="center" gap={1}><Icon className="pmc-card__party-icon" icon={UsersRound} label={t("Party {{number}}", {number: party.number})} /><Text className="pmc-card__party-number" type="supporting">{String(party.number).padStart(2, '0')}</Text></HStack></Tooltip> : null}
              {reorder ? <ReorderHandle name={name} reorder={reorder} /> : null}
            </HStack>
          </HStack>
          {profile ? <Button className="pmc-card__name-button" label={name} onClick={() => onSelectPlayer(profile)} variant="ghost" size="sm" endContent={context.fitToHeight ? undefined : <Icon icon={ArrowUpRight} />}><Text className="pmc-card__name" maxLines={1} weight="bold">{name}</Text></Button> : <Text className="pmc-card__name" maxLines={1} weight="bold">{name}</Text>}
          {identityDetails.length > 0 ? <Text className="pmc-card__agent" type="supporting" maxLines={1}>{identityDetails.join(' · ')}</Text> : null}
          {player.leader || (beforeGame && player.ready != null) || role ? <HStack className="pmc-card__readiness" gap={1} wrap="wrap">
            {player.leader && inParty ? <Token label={t("Leader")} icon={<Icon icon={Crown} />} size="sm" /> : null}
            {beforeGame && context.phase !== 'readycheck' && player.ready != null ? <Token label={player.ready ? t("Ready") : t("Not ready")} icon={player.ready ? <Icon icon={Check} /> : undefined} size="sm" /> : null}
            {role ? <Token label={displayText(role)} size="sm" /> : null}
          </HStack> : null}
        </VStack>

        <Grid className="pmc-card__ranks" columns={2} gap={2}>
          <CardRank game={context.game} rank={player.currentRank ?? player.rank} caption={context.completed && !player.currentRank ? t("Match rank") : t("Current")} compact={context.fitToHeight} />
          <CardRank game={context.game} rank={player.peakRank} caption={player.peakRankSeason ?? t("Peak")} compact={context.fitToHeight} />
        </Grid>

        {(pastTags.length > 0 || matchTags.length > 0) ? <VStack className="pmc-card__tags" gap={2}>
          {pastTags.length > 0 ? <HStack className="pmc-tags-history" gap={1} wrap="wrap" aria-label={t("Tags from past games")}>{pastTags.map(tag => <TagExplanation key={tag.label} tag={tag} source="past" {...tagSelection} />)}</HStack> : null}
          {matchTags.length > 0 ? <HStack className="pmc-tags-match" gap={1} wrap="wrap" aria-label={t("Tags earned this match")}>{matchTags.map(tag => <TagExplanation key={tag.label} tag={tag} source="match" {...tagSelection} />)}</HStack> : null}
        </VStack> : null}

        {statsLoading ? <VisuallyHidden id={statsStatusId} role="status" aria-live="off">{t("Fetching stats")}</VisuallyHidden> : null}

        {rows.length > 0 ? <VStack className="pmc-card__stats" gap={1} role="table" aria-label={t("{{name}} statistics", {name: name})} aria-busy={statsLoading}>
          {context.fitToHeight ? <HStack className="pmc-card__kda" align="center" justify="between" gap={1} role="row">
            <Text role="rowheader" type="supporting">{matchStats ? t('K/D/A') : `${t('Overall')} K/D/A`}</Text>
            {statsLoading && !matchStats && !overallStats ? <StatValue value="—" loading /> : <Text role="cell" aria-colspan={matchStats ? 2 : 1} hasTabularNumbers weight="bold">{kda}</Text>}
          </HStack> : null}
          <Grid className="pmc-stat-row pmc-stat-row--header" columns={matchStats ? 3 : 2} gap={2} role="row">
            <Text role="columnheader" type="supporting">{t("Stats")}</Text>
            <Tooltip content={source} hasHoverIndication={false}><Text role="columnheader" type="supporting">{t("Overall")}</Text></Tooltip>
            {matchStats ? <Text role="columnheader" type="supporting">{t("Match")}</Text> : null}
          </Grid>
          {rows.map((row, index) => <Grid className="pmc-stat-row" data-stat={row.label} columns={matchStats ? 3 : 2} gap={2} key={row.label} role="row">
            {row.label === 'Standing' ? <Tooltip content={t("Current position in the lobby, not the final placement.")} hasHoverIndication={false}><Text role="rowheader" type="supporting">{t(row.label)}</Text></Tooltip> : <Text role="rowheader" type="supporting">{t(row.label)}</Text>}
            <StatValue value={row.overall} loading={statsLoading} index={index} />
            {matchStats ? <Text role="cell" hasTabularNumbers weight="semibold">{row.match}</Text> : null}
          </Grid>)}
          <VStack className="pmc-card__source" gap={1}>
            {overallStats?.matchesPlayed ? <Text type="supporting">{t('Recent {{count}} games', {count: overallStats.matchesPlayed})}</Text>
              : statsLoading ? <Skeleton className="pmc-stat-skeleton" width="var(--spacing-24)" height="var(--spacing-2)" radius="none" index={7} /> : null}
            {snapshotTime ? <Tooltip content={t("TFT refreshes this snapshot periodically. It does not update after every damage event.")} hasHoverIndication={false}><Text type="supporting" hasTabularNumbers>{t("Updated")} {snapshotTime}</Text></Tooltip> : null}
          </VStack>
        </VStack> : !statsLoading && !beforeGame ? <VStack className="pmc-card__unavailable" gap={1}><Icon icon={EyeOff} color="secondary" /><Text type="supporting">{t("Statistics unavailable")}</Text></VStack> : null}
        {!beforeGame && !matchStats && player.score && player.score !== '—' ? <Text hasTabularNumbers type="supporting">{t("Match ·")} {player.score}</Text> : null}
      </VStack>
    </Card>
  )
}

export function PlayerMatchCards({teams, onSelectPlayer, ...context}: PlayerMatchCardsProps) {
  useLocale()
  const [activeTagId, setActiveTagId] = useState<string | null>(null)
  const {layout, canReorder, freeForAll, duos, sortedTeams, ownTeam, reorderableTeam, orders, hasCustomOrder, partyGroups, reorder, resetOrder, instructions} =
    useMatchRoster({teams, ...context}, () => setActiveTagId(null))
  const tagSelection = {activeTagId, setActiveTagId}
  const fitToHeight = context.fitToHeight === true && fitsValorantRoster({teams, ...context})
  const cardContext = {...context, fitToHeight, ...(duos ? {teamMode: 'duos' as const} : {})}
  const inParty = Boolean(context.phase && ['lobby', 'matchmaking', 'readycheck'].includes(context.phase))
  const beforeGame = !context.completed && Boolean(context.phase && context.phase !== 'live')

  return <VStack className={`pmc-lineup${fitToHeight ? ' pmc-lineup--fit' : ''}`} gap={fitToHeight ? 2 : 6}>
    {instructions}
    {!fitToHeight && sortedTeams.some(reorderableTeam) ? <HStack className="pmc-reorder-toolbar" align="center" justify="between" gap={3}>
      <Text type="supporting">{hasCustomOrder ? freeForAll ? t("Custom order · drag within this lobby") : t("Custom order · drag within each team") : layout.canAlignRoles ? t("Matched by role · drag to arrange") : freeForAll ? t("Drag cards to arrange the lobby") : t("Drag cards to arrange each team")}</Text>
      {resetOrder}
    </HStack> : null}
    <Grid className="pmc-teams" data-layout={layout.kind} columns={duos || sortedTeams.length > 2 ? {minWidth: 400, max: 2, repeat: 'fit'} : 1} gap={fitToHeight ? 2 : 6}>
    {sortedTeams.map((team, teamIndex) => {
      const unknownPairing = duos && !isConfirmedDuo(team)
      const allied = team === ownTeam && !freeForAll
      const opposing = !unknownPairing && Boolean(ownTeam && !allied)
      const identityOffset = sortedTeams.slice(0, teamIndex).reduce((sum, item) => sum + item.players.length, 0)
      const heading = displayText(duos ? unknownPairing ? 'Players' : allied ? 'Your duo' : `Duo ${teamIndex + 1}`
        : inParty && sortedTeams.length === 1 ? 'Your party' : freeForAll ? context.game === 'Teamfight Tactics' ? 'Players' : 'Free for all' : allied ? 'Your team' : opposing ? sortedTeams.length > 2 ? team.name : 'Opponents' : team.name)
      const group = <VStack className="pmc-team" gap={3} role={duos ? 'group' : undefined} aria-label={duos ? heading : undefined}>
          <HStack className="pmc-team__header" align="center" justify="between" gap={3}>
            <HStack align="center" gap={3}>
              <Heading level={2}>{heading}</Heading>
              <Text type="supporting">{t('{{count}} players', {count: team.players.length})}{!beforeGame && team.won != null ? ` · ${team.won ? t('Victory') : t('Defeat')}` : ''}</Text>
            </HStack>
            <HStack align="center" gap={3}>
              {fitToHeight && teamIndex === 0 && canReorder ? resetOrder : null}
              {!beforeGame && !freeForAll && team.score != null ? <Text className="pmc-team__score" hasTabularNumbers weight="bold">{team.score}</Text> : null}
            </HStack>
          </HStack>
          {unknownPairing ? <Text type="supporting">{t("Pairings unavailable")}</Text> : null}
          <Grid className="pmc-team__cards" columns={fitToHeight ? Math.max(...sortedTeams.map(item => item.players.length)) : matchGridColumns(team.players.length, context.game)} gap={fitToHeight ? 2 : 3}>
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
