import {t, useLocale, displayText} from '../i18n'
import {useMemo, useState} from 'react'
import {Avatar} from '@astryxdesign/core/Avatar'
import {Badge} from '@astryxdesign/core/Badge'
import {Button} from '@astryxdesign/core/Button'
import {EmptyState} from '@astryxdesign/core/EmptyState'
import {Grid} from '@astryxdesign/core/Grid'
import {Heading} from '@astryxdesign/core/Heading'
import {HStack} from '@astryxdesign/core/HStack'
import {Icon} from '@astryxdesign/core/Icon'
import {List, ListItem} from '@astryxdesign/core/List'
import {Section} from '@astryxdesign/core/Section'
import {SegmentedControl, SegmentedControlItem} from '@astryxdesign/core/SegmentedControl'
import {StatusDot} from '@astryxdesign/core/StatusDot'
import {Text} from '@astryxdesign/core/Text'
import {TextInput} from '@astryxdesign/core/TextInput'
import {VStack} from '@astryxdesign/core/VStack'
import {ArrowUpRight, ChevronLeft, ChevronRight, Fingerprint, List as ListIcon, Plus, Rows3, Search, Trophy} from 'lucide-react'
import {gameArtwork, valorantAgentAsset} from '../assets'
import type {Account, AppState, Game, Match} from '../types'
import {usePlayerPrivacy} from '../components/PlayerPrivacy'
import {AuthenticatedScreen, EmptyAccounts, MatchList, RankMedia, rankLabel, rankRatingLabel, strongestRank, type AuthenticatedView} from './shared'

export interface OverviewScreenProps {
  state: AppState
  view: AuthenticatedView
  onView: (view: AuthenticatedView) => void
  onSelect: (account: Account) => void
  onAdd: () => void
  onSelectMatch?: (match: Match, account: Account) => void
}
const rosterGames: readonly Game[] = ['VALORANT', 'League of Legends', 'Teamfight Tactics']
const gameLabel = (game: Game) => game === 'League of Legends' ? 'League' : game === 'Teamfight Tactics' ? 'TFT' : 'VALORANT'
const recentAgent = (account: Account) => (account.matches ?? []).flatMap(match => match.teams ?? []).flatMap(team => team.players).find(player => player.self)?.agent

export function OverviewScreen({state, view, onView, onSelect, onAdd, onSelectMatch}: OverviewScreenProps) {
  useLocale()
  const {displayName} = usePlayerPrivacy()
  const [query, setQuery] = useState('')
  const [focusedId, setFocusedId] = useState<string | null>(null)
  const strongest = useMemo(() => strongestRank(state.accounts), [state.accounts])
  const visible = state.accounts.filter(account => (
    `${displayName(account.riotId)} ${account.region}`.toLocaleLowerCase().includes(query.trim().toLocaleLowerCase())
  ))
  const focused = visible.find(account => account.id === focusedId) ?? visible.find(account => account.connected) ?? visible[0]
  const focusGame = focused?.matches?.[0]?.game ?? 'VALORANT'
  const latest = focused?.matches?.slice(0, 3) ?? []
  const connected = state.accounts.filter(account => account.connected).length
  const previewAccount = (direction: number) => {
    if (!visible.length) return
    const index = visible.findIndex(account => account.id === focused?.id)
    setFocusedId(visible[(index + direction + visible.length) % visible.length].id)
  }

  return (
    <AuthenticatedScreen
      actions={<Button icon={<Icon icon={Plus} />} label={t("Add account")} onClick={onAdd} variant="primary" size="lg" />}
      screen="overview" title={t("Accounts")}>
      <VStack gap={6}>
        <HStack className="pd-overview-strip" gap={6} align="center" wrap="wrap">
          <HStack gap={2} align="center"><Icon icon={Fingerprint} size="sm" color="secondary" /><Text weight="semibold">{t('{{count}} accounts', {count: state.accounts.length})}</Text></HStack>
          <HStack gap={2} align="center"><StatusDot label={t("{{connected}} connected accounts", {connected: connected})} variant="accent" /><Text weight="semibold">{connected}</Text><Text color="secondary">{t("connected")}</Text></HStack>
          {strongest && <HStack gap={2} align="center"><Icon icon={Trophy} size="sm" color="secondary" /><Text color="secondary">{t("Highest rank")}</Text><Text weight="medium">{displayText(rankLabel(strongest))}</Text></HStack>}
        </HStack>
        {state.accounts.length === 0 ? <EmptyAccounts onAdd={onAdd} /> : (
          <Grid className="pd-account-workspace" gap={6}>
            <Section className="pd-account-library" padding={0} variant="transparent">
              <VStack gap={5}>
                <HStack align="center" justify="between" gap={3}>
                  <HStack gap={2} align="center"><Heading level={2}>{t("Your accounts")}</Heading><Badge label={visible.length} variant="neutral" /></HStack>
                  <SegmentedControl label={t("Account row density")} value={view} onChange={value => onView(value as AuthenticatedView)} size="sm">
                    <SegmentedControlItem icon={<Icon icon={Rows3} />} isLabelHidden label={t("Comfortable rows")} value="grid" />
                    <SegmentedControlItem icon={<Icon icon={ListIcon} />} isLabelHidden label={t("Compact rows")} value="list" />
                  </SegmentedControl>
                </HStack>
                <TextInput label={t("Find an account")} isLabelHidden placeholder={t("Find a name or region…")} startIcon={Search} value={query} onChange={setQuery} hasClear width="100%" size="lg" />
                {visible.length === 0 ? <EmptyState title={t("No accounts found")} description={t("Try another name or region.")} icon={<Icon icon={Search} />} actions={<Button label={t("Clear search")} onClick={() => setQuery('')} />} /> :
                  <List className="pd-account-list" density={view === 'list' ? 'compact' : 'spacious'} hasDividers aria-label={t("Your Riot accounts")}>
                    {visible.map(account => <ListItem key={account.id}
                      className="pd-account-row"
                      label={displayName(account.riotId)}
                      isSelected={account.id === focused?.id}
                      onClick={() => {setFocusedId(account.id); onSelect(account)}}
                      startContent={<Avatar name={displayName(account.riotId)} src={valorantAgentAsset(recentAgent(account))} size="lg" tooltip={false} />}
                      description={<VStack gap={3}>
                        <HStack gap={2} align="center"><Text type="supporting">{account.region} {t("· Level")} {account.level ?? '—'}</Text><StatusDot variant={account.connected ? 'accent' : 'neutral'} label={account.connected ? t("Connected") : t("Offline")} /><Text type="supporting">{account.connected ? t("Connected") : t("Offline")}</Text></HStack>
                        {view === 'grid' && <HStack className="pd-account-row__ranks" gap={4} wrap="wrap">
                          {rosterGames.map(item => {
                            const rank = account.ranks.find(candidate => candidate.game === item)
                            return <HStack key={item} gap={1} align="center"><RankMedia rank={rank} /><VStack gap={0}><Text className="pd-mini-label" type="supporting">{gameLabel(item)}</Text><Text type="supporting">{displayText(rankLabel(rank))}</Text></VStack></HStack>
                          })}
                        </HStack>}
                      </VStack>}
                      endContent={<Icon icon={ChevronRight} size="sm" color="secondary" />}
                    />)}
                  </List>
                }
                <HStack justify="between" align="center" gap={3}><Text type="supporting">{t('{{visible}} of {{count}} accounts', {visible: visible.length, count: state.accounts.length})}</Text><Button variant="ghost" size="sm" label={t("Add another")} icon={<Icon icon={Plus} size="sm" />} onClick={onAdd} /></HStack>
              </VStack>
            </Section>
            {focused && <VStack className="pd-account-focus" gap={0} key={focused.id + focusGame}>
              <Section className="pd-focus-art" variant="transparent" padding={0}>
                <img className="pd-focus-art__image" src={gameArtwork(focusGame, latest[0]?.map)} alt="" />
                <VStack className="pd-focus-art__content" justify="between" gap={6} padding={6}>
                  <HStack justify="between" align="center"><Text className="peaks-eyebrow" type="supporting">{t("ACCOUNT PREVIEW")}</Text><HStack gap={2} align="center"><Text className="pd-focus-game" type="supporting">{gameLabel(focusGame)}</Text>{visible.length > 1 && <><Button label={t("Preview previous account")} tooltip={t("Previous account")} icon={<Icon icon={ChevronLeft} />} isIconOnly variant="secondary" size="sm" onClick={() => previewAccount(-1)} /><Button label={t("Preview next account")} tooltip={t("Next account")} icon={<Icon icon={ChevronRight} />} isIconOnly variant="secondary" size="sm" onClick={() => previewAccount(1)} /></>}</HStack></HStack>
                  <VStack gap={4}>
                    <HStack gap={3} align="center"><Avatar name={displayName(focused.riotId)} src={valorantAgentAsset(recentAgent(focused))} size="lg" tooltip={false} /><VStack gap={1}><Heading className="pd-focus-name" level={2}>{displayName(focused.riotId).split('#')[0]}</Heading><Text color="secondary">{displayName(focused.riotId).includes('#') ? `#${displayName(focused.riotId).split('#').slice(1).join('#')} · ` : ''}{focused.region} {t("· Level")} {focused.level ?? '—'}</Text></VStack></HStack>
                    <Button className="pd-focus-open" label={t("Open account")} endContent={<Icon icon={ArrowUpRight} />} onClick={() => onSelect(focused)} variant="primary" size="lg" />
                  </VStack>
                </VStack>
              </Section>
              <Grid className="pd-focus-ranks" columns={3} gap={0}>
                {rosterGames.map(item => {
                  const rank = focused.ranks.find(candidate => candidate.game === item)
                  return <VStack key={item} align="center" gap={2} padding={4}>
                    <Text className="pd-mini-label" type="supporting">{gameLabel(item)}</Text>
                    <RankMedia rank={rank} />
                    <Text weight="semibold">{displayText(rankLabel(rank))}</Text>
                    <Text type="supporting" hasTabularNumbers>{rank?.rating != null ? rankRatingLabel(item, rank.rating) : t("Not placed")}</Text>
                  </VStack>
                })}
              </Grid>
              <VStack className="pd-focus-activity" gap={4} padding={5}>
                <HStack justify="between" align="center"><Heading level={3}>{t("Recent matches")}</Heading><Text type="supporting">{latest.length ? t("Last played") : t("No matches yet")}</Text></HStack>
                {latest.length ? <MatchList heading={null} matches={latest} onSelect={match => onSelectMatch ? onSelectMatch(match, focused) : onSelect(focused)} /> : <Text color="secondary">{t("Your recent games will appear here after the next refresh.")}</Text>}
              </VStack>
            </VStack>}
          </Grid>
        )}
      </VStack>
    </AuthenticatedScreen>
  )
}
