import {useEffect, useRef, useState, type ReactNode} from 'react'
import {Theme} from '../ui'
import {Alert, Button as AntButton, Card, Col, Flex, Result, Row, Segmented, Spin, Statistic, Tag, Tooltip, Typography} from 'antd'
import {ChevronRight, MapPin, Plus, RefreshCw, Settings2, Star, Swords, UserRound} from 'lucide-react'
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
  const region = game === 'riot' ? undefined : accountRegionForGame(account, game)
  const meta: [typeof MapPin, string, string][] = [
    ...(game === 'Teamfight Tactics' ? [] : [[MapPin, t('Region'), region ?? t('Region not detected')] as [typeof MapPin, string, string]]),
    ...(level != null ? [[Star, t('Level'), formatNumber(level)] as [typeof MapPin, string, string]] : []),
    [Swords, t('Loaded matches'), formatNumber(matches.length)],
  ]
  return <div className={`pd-riot-hero${game === 'VALORANT' && favorite ? ' pd-riot-hero--agent' : ''}`}>
    {art ? <img className="pd-riot-hero__art" src={art} alt="" aria-hidden /> : null}
    <Flex vertical gap={20} className="pd-riot-hero__body">
      <Flex gap={8} wrap>{meta.map(([Glyph, label, value]) => <Tooltip key={label} title={label}>
        <Tag className="pd-riot-hero__meta" icon={<Glyph size={12} aria-hidden />}><span className="pk-visually-hidden">{label} </span>{value}</Tag>
      </Tooltip>)}{isActive && !owned ? <Tag color="success">{t('Active Riot account')}</Tag> : null}</Flex>
      {primary}
      <Flex gap={32} wrap align="end">
        {[{label: t('Current rating'), value: rank, season: game === 'VALORANT' ? account.valorantAct : undefined},
          ...(peak ? [{label: t('Peak rating'), value: peak, season: rank?.peakSeason}] : [])].map(item => <Flex key={item.label} gap={12} align="center">
          {item.value ? <RankMedia rank={item.value} /> : null}
          <Statistic title={item.label} value={item.value ? displayText(rankLabel(item.value)) : t('Rank unavailable')}
            suffix={item.value?.rating != null || item.season ? <Typography.Text type="secondary">{[item.value?.rating != null ? rankRatingLabel(item.value.game, item.value.rating) : '', item.season ?? ''].filter(Boolean).join(' · ')}</Typography.Text> : undefined} />
        </Flex>)}
        {favorite ? <Statistic className="pd-riot-hero__favorite" title={t('Most played')} value={favorite.name}
          suffix={<Typography.Text type="secondary">× {formatNumber(favorite.count)}</Typography.Text>} /> : null}
      </Flex>
    </Flex>
  </div>
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
  const [refreshing, setRefreshing] = useState(false)
  const {displayName} = usePlayerPrivacy()
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
    <Result icon={<UserRound size={48} aria-hidden />} title={t('Connect your Riot account')}
      extra={onAdd ? <AntButton type="primary" icon={<Plus size={16} />} onClick={onAdd}>{t('Add account')}</AntButton> : null} />
  </AuthenticatedScreen>

  const games = PROFILE_GAMES.map(game => ({game, rank: account.ranks.find(rank => rank.game === game), peak: account.peakRanks?.find(rank => rank.game === game), matches: profileMatches(account.matches ?? [], game)}))
  const gameName = (game: ProfileGame) => game === 'riot' ? t('Riot profile') : game
  const gameIcon = (game: ProfileGame) => game === 'riot' ? riotFist : gameProfileIcon(game)
  const switcher = <Segmented className="pd-game-switch" size="large" value={view.game} onChange={value => selectGame(value as ProfileGame)}
    aria-label={t('Game profiles')}
    options={(['riot', ...PROFILE_GAMES] as ProfileGame[]).map(game => ({value: game, title: gameName(game),
      label: <img className={`pd-riot-game-icon${game === 'riot' ? ' pd-riot-fist-icon' : ''}`} src={gameIcon(game)} alt={gameName(game)} />}))} />
  const notices = ([
    failed ? ['info', t('Accumulated history could not be loaded. Showing available recent matches.')] : null,
    refreshFailed ? ['error', t('That action could not be completed')] : null,
    reportError ? ['error', t('This saved match report could not be loaded. Try refreshing the profile.')] : null,
  ].filter(Boolean)) as ['info' | 'error', string][]
  const runRefresh = () => { setRefreshing(true); void Promise.resolve(refresh()).finally(() => setRefreshing(false)) }
  return <Theme theme={profileTheme(view.game)} mode="dark">
    <AuthenticatedScreen title={owned ? t('Account') : displayName(account.riotId)} screen={owned ? 'account' : 'player-profile'} contentWidth="100%"
      heading={<Flex gap={16} align="center" wrap>
        {owned ? null : <Typography.Title level={3} className="peaks-screen__title">{displayName(account.riotId)}</Typography.Title>}
        {switcher}
      </Flex>}
      actions={<>
        {isSynchronizing ? <Tooltip title={t('Loading match history…')}><Spin size="small" /></Tooltip> : null}
        {actions}
        {onManage ? <Tooltip title={t('Manage account')}><AntButton type="text" icon={<Settings2 size={18} />} aria-label={t('Manage account')} onClick={onManage} /></Tooltip> : null}
        {onRefresh ? <Tooltip title={t(refreshFailed ? 'Try again' : 'Refresh data')}><AntButton icon={<RefreshCw size={18} />} aria-label={t(refreshFailed ? 'Try again' : 'Refresh data')} loading={refreshing} onClick={runRefresh} /></Tooltip> : null}
      </>}>
      <AccountArrival arrival={view.arrival} fitContent>
        <Flex vertical gap={16} className="pd-riot-profile" data-profile-game={view.game}>
          {notices.map(([type, message]) => <Alert key={message} type={type} title={message} showIcon role={type === 'error' ? 'alert' : 'status'} />)}
          {view.game === 'riot' ? <>
            <ActivityHighlights activity={activity} owned={owned} />
            <Row gutter={[16, 16]} aria-label={t('Current ranks')} role="list">
              {games.map(row => <Col key={row.game} xs={24} md={8} role="listitem">
                <Card hoverable size="small" className="pd-rank-card" onClick={() => selectGame(row.game)}
                  aria-label={row.game} tabIndex={0} onKeyDown={event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); selectGame(row.game) } }}>
                  <Flex gap={16} align="center">
                    {row.rank ? <RankMedia rank={row.rank} /> : <img className="pd-riot-game-icon pd-riot-game-icon--large" src={gameProfileIcon(row.game)} alt="" />}
                    <Flex vertical gap={2} style={{minWidth: 0, flex: 1}}>
                      <Flex gap={8} align="center"><img className="pd-riot-game-icon pd-riot-game-icon--small" src={gameProfileIcon(row.game)} alt="" />
                        <Typography.Text strong>{row.rank ? displayText(rankLabel(row.rank)) : t('Rank unavailable')}</Typography.Text></Flex>
                      <Typography.Text type="secondary">{row.rank?.rating != null ? rankRatingLabel(row.game, row.rank.rating) : '—'}{row.peak ? ` · ${t('Peak')} ${displayText(rankLabel(row.peak))}` : ''}</Typography.Text>
                    </Flex>
                    <ChevronRight size={16} className="pd-rank-card__chevron" aria-hidden />
                  </Flex>
                </Card>
              </Col>)}
            </Row>
            <ActivityCalendar activity={activity} onSelectMatch={match => { void openRecordedMatch(match) }} />
            <RiotActivity activity={activity} />
            <MatchList riotId={account.riotId} heading={t('Recent matches')} matches={[...(account.matches ?? [])].sort((a, b) => (b.playedAtTimestamp ?? 0) - (a.playedAtTimestamp ?? 0)).slice(0, 9)} onSelect={onSelectMatch} />
            {contextContent}
          </> : <>
            <ProfileHero account={account} game={view.game} isActive={isActive} owned={owned}
              primary={view.game === 'Teamfight Tactics' ? <TftRecentResults account={account} onSelectMatch={onSelectMatch} /> : undefined} />
            <RankHistoryChart game={view.game} activity={activity} />
            {view.game === 'VALORANT'
              ? <ValorantAccountProfile account={account} isSynchronizing={isSynchronizing} onSelectMatch={onSelectMatch} />
              : view.game === 'League of Legends'
                ? <LeagueAccountProfile account={account} isSynchronizing={isSynchronizing} onSelectMatch={onSelectMatch} />
                : <TftAccountProfile account={account} mode={tftMode} onModeChange={setTftMode} isSynchronizing={isSynchronizing} onSelectMatch={onSelectMatch} />}
          </>}
        </Flex>
      </AccountArrival>
    </AuthenticatedScreen>
  </Theme>
}
