import {useEffect, useRef, useState, type ReactNode} from 'react'
import {Button} from '@astryxdesign/core/Button'
import {EmptyState} from '@astryxdesign/core/EmptyState'
import {Heading} from '@astryxdesign/core/Heading'
import {Grid} from '@astryxdesign/core/Grid'
import {HStack} from '@astryxdesign/core/HStack'
import {Icon} from '@astryxdesign/core/Icon'
import {IconButton} from '@astryxdesign/core/IconButton'
import {Section} from '@astryxdesign/core/Section'
import {Text} from '@astryxdesign/core/Text'
import {Token} from '@astryxdesign/core/Token'
import {VStack} from '@astryxdesign/core/VStack'
import {Theme} from '@astryxdesign/core/theme'
import {RefreshCw, Settings2, UserRound} from 'lucide-react'
import {accountRegionForGame} from '../accountRegions'
import {profileMatches, profilePlayer} from '../accountProfile'
import {gameArtwork, valorantAgentPortraitAsset} from '../assets'
import riotFist from '../assets/riot-fist.png'
import {AccountArrival} from '../components/AccountArrival'
import {ActivityCalendar} from '../components/ActivityCalendar'
import {ActivityHighlights, RiotActivity} from '../components/RiotActivity'
import {RankHistoryChart} from '../components/RankHistoryChart'
import {TftRecentResults} from '../components/TftRecentResults'
import {invoke} from '../bridge'
import {usePlayerPrivacy} from '../components/PlayerPrivacy'
import {displayText, formatNumber, t, useLocale} from '../i18n'
import {championArtwork, gameProfileIcon} from '../profileAssets'
import {favoriteCharacter, PROFILE_GAMES, type ProfileGame} from '../riotProfile'
import {profileTheme} from '../theme/profileThemes'
import type {Account, Match, ProfileActivity, Rank} from '../types'
import {useProfileActivity} from '../useProfileActivity'
import {useProfileRefresh} from '../useProfileRefresh'
import {AuthenticatedScreen, MatchList, RankMedia, rankLabel, rankRatingLabel} from './shared'
import {LeagueAccountProfile} from './LeagueAccountProfile'
import {TftAccountProfile} from './TftAccountProfile'
import {ValorantAccountProfile} from './ValorantAccountProfile'

export function ProfileHero({account, game, isActive, owned = true, primary}: {account: Account; game: ProfileGame; isActive: boolean; owned?: boolean; primary?: ReactNode}) {
  const {displayName} = usePlayerPrivacy()
  const favorite = game === 'riot' ? undefined : favoriteCharacter(account, game)
  const art = game === 'riot' ? undefined : game === 'VALORANT' && favorite
    ? valorantAgentPortraitAsset(favorite.id) : game === 'League of Legends' && favorite
    ? championArtwork(favorite.id) : gameArtwork(game)
  const rank = account.ranks.find(item => item.game === game)
  const peak: Rank | undefined = rank?.peakTier ? {game: rank.game, tier: rank.peakTier, division: rank.peakDivision, rating: rank.peakRating}
    : account.peakRanks?.find(item => item.game === game)
  const matches = game === 'riot' ? [] : profileMatches(account.matches ?? [], game)
  const level = game === 'VALORANT' ? account.valorantLevel ?? matches.map(match => profilePlayer(match, account.riotId)?.accountLevel).find(value => value != null)
    : game === 'League of Legends' ? account.leagueLevel : undefined
  return <VStack className={`pd-riot-hero${game === 'riot' ? ' pd-riot-hero--riot' : ''}${game === 'VALORANT' && favorite ? ' pd-riot-hero--agent' : ''}`} gap={6} padding={6} justify="between">
    {art ? <img className="pd-riot-hero__art" src={art} alt="" aria-hidden /> : null}
    <VStack className="pd-riot-hero__identity" gap={3} align="start">
      <Token label={isActive ? t('Active Riot account') : t(owned ? 'Saved profile' : 'Player profile')} color={isActive ? 'green' : 'gray'} size="sm" />
      <VStack gap={1}>
        <Text className="peaks-eyebrow">{game === 'riot' ? t('Riot profile') : game}</Text>
        <Heading level={2} type="display-2">{displayName(account.riotId)}</Heading>
      </VStack>
      {game === 'riot' || game === 'Teamfight Tactics' ? null : <HStack gap={3} wrap="wrap">
        <Text color="secondary">PC · {accountRegionForGame(account, game) ?? t('Region not detected')}</Text>
        {level != null ? <Text color="secondary">{t('Level {{level}}', {level: formatNumber(level)})}</Text> : null}
        <Text color="secondary">{t('{{count}} loaded matches', {count: matches.length})}</Text>
      </HStack>}
    </VStack>
    {primary ? <VStack className="pd-riot-hero__primary" gap={3}>{primary}</VStack> : null}
    {game !== 'riot' ? <HStack className="pd-riot-hero__footer" align="end" justify="between" gap={6} wrap="wrap">
      <HStack gap={6} wrap="wrap">
        {[{label: 'Current rating', value: rank, season: game === 'VALORANT' ? account.valorantAct : undefined},
          ...(peak ? [{label: 'Peak rating', value: peak, season: rank?.peakSeason}] : [])].map(item => <HStack key={item.label} gap={3} align="center">
          {item.value ? <RankMedia rank={item.value} /> : null}
          <VStack gap={1}><Text type="supporting" color="secondary">{t(item.label)}</Text>
            <Text weight="semibold">{item.value ? displayText(rankLabel(item.value)) : t('Rank unavailable')}</Text>
            <Text type="supporting" color="secondary">{item.value?.rating != null ? rankRatingLabel(item.value.game, item.value.rating) : '—'}{item.season ? ` · ${item.season}` : ''}</Text>
          </VStack>
        </HStack>)}
      </HStack>
      {favorite ? <VStack className="pd-riot-hero__favorite" gap={1}>
        <Text weight="semibold">{t('Most played')} · {favorite.name}</Text>
        <Text type="supporting" color="secondary">{t('{{count}} matches in loaded history', {count: favorite.count})}</Text>
      </VStack> : null}
    </HStack> : null}
  </VStack>
}

export function AccountScreen({account, isActive, isSynchronizing = false, onRefresh, onSelectMatch, onManage, onAdd, owned = true, actions, contextContent, activity: providedActivity}: {
  account?: Account
  isActive: boolean
  isSynchronizing?: boolean
  onRefresh?: () => Promise<void>
  onSelectMatch: (match: Match) => void
  onManage?: () => void
  onAdd?: () => void
  owned?: boolean
  actions?: ReactNode
  contextContent?: ReactNode
  activity?: ProfileActivity
}) {
  useLocale()
  const [view, setView] = useState<{game: ProfileGame; arrival: number}>({game: 'riot', arrival: 0})
  const {refresh, revision, failed: refreshFailed} = useProfileRefresh(account?.id, onRefresh)
  const [tftMode, setTftMode] = useState('solo')
  const [reportError, setReportError] = useState(false)
  const mountedIdentity = useRef(account?.id)
  useEffect(() => { mountedIdentity.current = account?.id; return () => { mountedIdentity.current = undefined } }, [account?.id])
  const {activity, failed} = useProfileActivity(account, owned, revision, providedActivity)
  const openRecordedMatch = async (match: Match) => {
    setReportError(false)
    const loaded = account?.matches?.find(item => item.game === match.game && item.id === match.id)
    if (!owned || loaded?.teams?.length) { onSelectMatch(loaded ?? match); return }
    const id = account?.id
    try {
      const full = await invoke<Match | null>('account_match', {accountId: id, matchId: match.id})
      if (mountedIdentity.current !== id) return
      if (full) onSelectMatch(full)
      else setReportError(true)
    } catch { if (mountedIdentity.current === id) setReportError(true) }
  }
  const selectGame = (game: ProfileGame) => setView(previous => previous.game === game ? previous : {game, arrival: previous.arrival + 1})
  if (!account) return <AuthenticatedScreen title={t('Account')} screen="account">
    <EmptyState title={t('Connect your Riot account')} icon={<Icon icon={UserRound} />}
      description={t('Your Riot profile opens here when Peaks identifies your active account or approves a sign-in.')}
      actions={<Button label={t('Add account')} onClick={onAdd} />} />
  </AuthenticatedScreen>

  const games = PROFILE_GAMES.map(game => ({game, rank: account.ranks.find(rank => rank.game === game), peak: account.peakRanks?.find(rank => rank.game === game), matches: profileMatches(account.matches ?? [], game)}))
  return <Theme theme={profileTheme(view.game)} mode="dark"><VStack height="100%" className="pd-riot-profile" data-profile-game={view.game}>
    <AuthenticatedScreen title={t(owned ? 'Account' : 'Riot profile')} eyebrow={t('Riot profile')} screen={owned ? 'account' : 'player-profile'} contentWidth="100%"
      actions={<>
        {actions}
        {onManage ? <Button icon={<Icon icon={Settings2} />} label={t('Manage account')} variant="ghost" onClick={onManage} /> : null}
        {onRefresh ? <Button icon={<Icon icon={RefreshCw} />} label={t(refreshFailed ? 'Try again' : 'Refresh data')} variant="secondary" clickAction={refresh} /> : null}
      </>}>
      <VStack gap={5}>
          <HStack gap={2} align="center" role="group" aria-label={t('Game profiles')}>
            <IconButton label={t('Riot profile')} tooltip={t('Riot profile')} icon={<img className="pd-riot-game-icon pd-riot-fist-icon" src={riotFist} alt="" />} size="lg"
              variant={view.game === 'riot' ? 'primary' : 'ghost'} aria-pressed={view.game === 'riot'} onClick={() => selectGame('riot')} />
            {PROFILE_GAMES.map(game => <IconButton key={game} label={game} tooltip={game} size="lg"
              className="pd-riot-game-button" variant={view.game === game ? 'primary' : 'ghost'} aria-pressed={view.game === game}
              icon={<img className="pd-riot-game-icon" src={gameProfileIcon(game)} alt="" />} onClick={() => selectGame(game)} />)}
          </HStack>
        <AccountArrival arrival={view.arrival} fitContent>
          <VStack gap={6} className="pd-riot-profile__body">
            <ProfileHero account={account} game={view.game} isActive={isActive} owned={owned}
              primary={view.game === 'Teamfight Tactics' ? <TftRecentResults account={account} onSelectMatch={onSelectMatch} /> : undefined} />
            {view.game === 'riot' ? <ActivityCalendar activity={activity} onSelectMatch={match => { void openRecordedMatch(match) }} /> : null}
            {failed ? <Text role="status" color="secondary">{t('Accumulated history could not be loaded. Showing available recent matches.')}</Text> : null}
            {refreshFailed ? <Text role="alert" color="secondary">{t('That action could not be completed')}</Text> : null}
            {reportError ? <Text role="alert" color="secondary">{t('This saved match report could not be loaded. Try refreshing the profile.')}</Text> : null}
            {isSynchronizing ? <Text role="status" color="secondary">{t('Loading match history…')}</Text> : null}
            {view.game === 'riot' ? <VStack gap={4}>
              <ActivityHighlights activity={activity} owned={owned} />
              <Grid columns={3} gap={4} className="pd-activity-ranks" aria-label={t('Current ranks')}>
                {games.map(row => <Section key={row.game} className="pd-activity-panel" padding={4} variant="transparent"><VStack gap={4}>
                  <Button label={row.game} icon={<img className="pd-riot-game-icon" src={gameProfileIcon(row.game)} alt="" />} variant="ghost" onClick={() => selectGame(row.game)} />
                  <HStack gap={3} align="center">
                  {row.rank ? <RankMedia rank={row.rank} /> : null}<VStack gap={1}>
                    <Text weight="semibold">{row.rank ? displayText(rankLabel(row.rank)) : t('Rank unavailable')}</Text>
                    <Text color="secondary" type="supporting">{row.rank?.rating != null ? rankRatingLabel(row.game, row.rank.rating) : '—'}</Text>
                    {row.peak ? <Text color="secondary" type="supporting">{t('Peak')} · {displayText(rankLabel(row.peak))}</Text> : null}
                  </VStack>
                  </HStack><Text type="supporting" color="secondary">{accountRegionForGame(account, row.game) ?? t('Region not detected')} · {t('{{count}} loaded matches', {count: row.matches.length})}</Text>
                </VStack></Section>)}
              </Grid>
              <RiotActivity activity={activity} />
              <MatchList riotId={account.riotId} heading={t('Recent matches')} matches={[...(account.matches ?? [])].sort((a, b) => (b.playedAtTimestamp ?? 0) - (a.playedAtTimestamp ?? 0)).slice(0, 9)} onSelect={onSelectMatch} />
              {contextContent}
            </VStack> : <VStack gap={5}><RankHistoryChart game={view.game} activity={activity} />{view.game === 'VALORANT'
              ? <ValorantAccountProfile account={account} isSynchronizing={isSynchronizing} onSelectMatch={onSelectMatch} />
              : view.game === 'League of Legends'
                ? <LeagueAccountProfile account={account} isSynchronizing={isSynchronizing} onSelectMatch={onSelectMatch} />
                : <TftAccountProfile account={account} mode={tftMode} onModeChange={setTftMode} isSynchronizing={isSynchronizing} onSelectMatch={onSelectMatch} />}</VStack>}
          </VStack>
        </AccountArrival>
      </VStack>
    </AuthenticatedScreen>
  </VStack></Theme>
}
