import {t, useLocale, displayText} from '../i18n'
import {usePlayerPrivacy} from '../components/PlayerPrivacy'
import {useState} from 'react'
import {AlertDialog} from '@astryxdesign/core/AlertDialog'
import {Avatar} from '@astryxdesign/core/Avatar'
import {Button} from '@astryxdesign/core/Button'
import {ButtonGroup} from '@astryxdesign/core/ButtonGroup'
import {Grid} from '@astryxdesign/core/Grid'
import {Heading} from '@astryxdesign/core/Heading'
import {HStack} from '@astryxdesign/core/HStack'
import {Icon} from '@astryxdesign/core/Icon'
import {List, ListItem} from '@astryxdesign/core/List'
import {MoreMenu} from '@astryxdesign/core/MoreMenu'
import {Section} from '@astryxdesign/core/Section'
import {StatusDot} from '@astryxdesign/core/StatusDot'
import {Tab, TabList} from '@astryxdesign/core/TabList'
import {Text} from '@astryxdesign/core/Text'
import {Token} from '@astryxdesign/core/Token'
import {VStack} from '@astryxdesign/core/VStack'
import {ArrowLeft, ArrowUpRight, BarChart3, Copy, History, KeyRound, LayoutGrid, QrCode, Radio, RefreshCw, ShieldCheck, Swords, Trash2, Trophy} from 'lucide-react'
import {valorantMapName} from '../assets'
import {CompetitiveInsights} from '../components/CompetitiveInsights'
import {PasteQrDialog} from '../components/PasteQrDialog'
import type {QrImageRequest} from '../qrImage'
import type {Account, Match} from '../types'
import {AuthenticatedScreen, GAMES, MatchList, RankMedia, rankLabel, rankRatingLabel, resultColor} from './shared'

type AccountTab = 'overview' | 'matches' | 'insights' | 'security'

export interface AccountDetailScreenProps {
  account: Account
  onBack: () => void
  onCopy: () => void | Promise<void>
  onConnect: () => void
  onDelete: () => void | Promise<void>
  onPasteQr: (payload: QrImageRequest) => Promise<void>
  onRefresh: () => void | Promise<void>
  onSelectMatch: (match: Match) => void
}

export function AccountDetailScreen({
  account,
  onBack,
  onCopy,
  onConnect,
  onDelete,
  onPasteQr,
  onRefresh,
  onSelectMatch,
}: AccountDetailScreenProps) {
  useLocale()
  const {displayName} = usePlayerPrivacy()
  const [tab, setTab] = useState<AccountTab>('overview')
  const [isDeleteOpen, setDeleteOpen] = useState(false)
  const [isDeleting, setDeleting] = useState(false)
  const [isPasteQrOpen, setPasteQrOpen] = useState(false)
  const connectionLabel = account.connected ? t('Connected') : t('Offline')
  const latestMatch = account.matches?.[0]

  const deleteAccount = async () => {
    setDeleting(true)
    try {
      await onDelete()
      setDeleteOpen(false)
    } catch {
      setDeleteOpen(true)
    } finally {
      setDeleting(false)
    }
  }

  return (
    <>
      <AuthenticatedScreen
        actions={
          <>
            <Button
              clickAction={async () => { await onRefresh() }}
              icon={<Icon icon={RefreshCw} />}
              isIconOnly
              label={t("Refresh data")}
              tooltip={t("Refresh account data")}
              variant="ghost"
            />
            <ButtonGroup label={t("Riot account actions")}>
              <Button
                icon={<Icon icon={Radio} />}
                label={(account.canConnectQr ?? account.connected) ? t("Connect Riot Client") : t("Sign in to Riot again")}
                onClick={onConnect}
                variant="primary"
              />
              <MoreMenu
                alignment="end"
                items={[
                  ...((account.canConnectQr ?? account.connected) ? [{
                    id: 'paste-qr',
                    label: t('Paste a QR'),
                    description: t('Drop a Riot QR image or paste one with Ctrl+V'),
                    icon: <Icon icon={QrCode} />,
                    onClick: () => setPasteQrOpen(true),
                  }] : []),
                  {
                    id: 'copy-totp',
                    label: t('Copy authenticator code'),
                    description: account.hasTotp
                      ? t('Copy the current code and clear it automatically')
                      : t('No authenticator secret is stored for this account'),
                    icon: <Icon icon={Copy} />,
                    isDisabled: !account.hasTotp,
                    onClick: () => { void onCopy() },
                  },
                  {
                    id: 'delete-account',
                    label: t('Delete account'),
                    icon: <Icon icon={Trash2} />,
                    onClick: () => setDeleteOpen(true),
                  },
                ]}
                label={t("More Riot account actions")}
                placement="below"
                variant="primary"
              />
            </ButtonGroup>
          </>
        }
        description={t("{{region}} · Level {{value2}} · {{value3}}", {region: account.region, value2: account.level ?? '—', value3: displayText(account.lastUpdated ?? 'Last synced just now')})}
        screen="account-detail"
        title={t("Account details")}>
        <VStack className="pd-detail" gap={6}>
        <HStack align="center" justify="between" gap={3}>
          <Button
            icon={<Icon icon={ArrowLeft} />}
            label={t("All accounts")}
            onClick={onBack}
            size="sm"
            variant="ghost"
          />
          <Text className="pd-detail__eyebrow" type="supporting">{t("YOUR ACCOUNT /")} {account.region}</Text>
        </HStack>

        <Grid className="pd-detail__identity" columns={2} gap={0}>
          <VStack className="pd-detail__identity-copy" justify="between" gap={8} padding={8}>
              <HStack align="center" gap={2}>
                <Icon color="secondary" icon={ShieldCheck} />
                <Text className="pd-detail__eyebrow" type="supporting">{t("PERSONAL ACCOUNT")}</Text>
              </HStack>
              <VStack gap={4}>
                <Avatar className="pd-detail__avatar" name={displayName(account.riotId)} size="lg" tooltip={false} />
                <Heading className="pd-detail__identity-name" level={2} type="display-2">{displayName(account.riotId)}</Heading>
                <HStack align="center" gap={3} wrap="wrap">
                  <Token color="gray" label={account.region} size="sm" />
                  <Text color="secondary">{t("Level")} {account.level ?? '—'}</Text>
                  <Text color="secondary">{t('{{count}} recorded matches', {count: account.matches?.length ?? 0})}</Text>
                </HStack>
              </VStack>
          </VStack>
          <Section className="pd-detail__identity-art pd-detail__art pd-riot-surface" padding={8} variant="transparent">
            <VStack className="pd-detail__art-content" gap={8} justify="between">
              <HStack align="center" justify="end" gap={2}>
                <StatusDot label={connectionLabel} variant={account.connected ? 'neutral' : 'warning'} />
                <Text weight="medium">{connectionLabel}</Text>
              </HStack>
              <VStack align="end" gap={2}>
                <Text className="pd-detail__eyebrow" type="supporting">{t("LAST PLAYED")}</Text>
                <Heading level={3} type="display-3">{latestMatch ? (latestMatch.game === 'VALORANT' ? valorantMapName(latestMatch.map) : latestMatch.map ?? latestMatch.game) : t("No matches yet")}</Heading>
                {latestMatch?.playedAt ? <Text type="supporting">{displayText(latestMatch.playedAt)}</Text> : null}
              </VStack>
            </VStack>
          </Section>
        </Grid>

        <Grid className="pd-detail__workspace" columns={2} gap={8}>
          <VStack className="pd-detail__sidebar" gap={6}>
            <VStack gap={4}>
              <HStack align="center" gap={2}><Icon color="secondary" icon={Trophy} /><Heading level={2}>{t("Ranks")}</Heading></HStack>
              <List className="pd-detail__rank-list" density="balanced" hasDividers>
                {GAMES.map(game => {
                  const rank = account.ranks.find(item => item.game === game)
                  return <ListItem key={game} label={displayText(rankLabel(rank))} description={game} startContent={<RankMedia rank={rank} />} endContent={rank?.rating != null ? <Text hasTabularNumbers type="supporting">{rankRatingLabel(game, rank.rating)}</Text> : undefined} />
                })}
              </List>
            </VStack>
          </VStack>
          <VStack className="pd-detail__main" gap={6}>
        <TabList className="pd-detail__tabs"
          hasDivider
          onChange={value => setTab(value as AccountTab)}
          role="tablist"
          value={tab}>
          <Tab icon={<Icon icon={LayoutGrid} />} label={t("Overview")} panelId="account-detail-overview-panel" value="overview" />
          <Tab icon={<Icon icon={History} />} label={t("Matches")} panelId="account-detail-matches-panel" value="matches" />
          <Tab icon={<Icon icon={BarChart3} />} label={t("Insights")} panelId="account-detail-insights-panel" value="insights" />
          <Tab icon={<Icon icon={ShieldCheck} />} label={t("Security")} panelId="account-detail-security-panel" value="security" />
        </TabList>

        {tab === 'overview' ? (
          <VStack
            className="peaks-account-panel pd-detail__panel"
            gap={6}
            id="account-detail-overview-panel"
            role="tabpanel">
            {latestMatch ? <Section className="pd-detail__latest" padding={5} variant="muted">
              <HStack align="center" justify="between" gap={4} wrap="wrap">
                <HStack align="center" gap={3}>
                  <Icon icon={Swords} color="secondary" />
                  <VStack gap={1}>
                    <Text className="pd-detail__eyebrow" type="supporting">{t("LATEST RESULT")}</Text>
                    <HStack align="center" gap={2}><Token color={resultColor(latestMatch.result)} label={displayText(latestMatch.result)} size="sm" /><Text hasTabularNumbers weight="semibold">{latestMatch.score ?? t("Score unavailable")}</Text></HStack>
                  </VStack>
                </HStack>
                <Button icon={<Icon icon={ArrowUpRight} />} label={t("Open report")} onClick={() => onSelectMatch(latestMatch)} size="sm" variant="secondary" />
              </HStack>
            </Section> : null}
            <MatchList heading={t("Recent activity")} matches={account.matches ?? []} onSelect={onSelectMatch} />
          </VStack>
        ) : null}

        {tab === 'matches' ? (
          <VStack
            className="peaks-account-panel pd-detail__panel"
            gap={4}
            id="account-detail-matches-panel"
            role="tabpanel">
            <MatchList heading={t("Match history")} matches={account.matches ?? []} onSelect={onSelectMatch} />
          </VStack>
        ) : null}

        {tab === 'insights' ? (
          <VStack
            className="peaks-account-panel pd-detail__panel"
            gap={4}
            id="account-detail-insights-panel"
            role="tabpanel">
            <HStack align="center" gap={2}>
              <Icon color="secondary" icon={BarChart3} />
                <Heading level={2}>{t("Your performance")}</Heading>
            </HStack>
            <CompetitiveInsights matches={account.matches ?? []} riotId={account.riotId} />
          </VStack>
        ) : null}

        {tab === 'security' ? (
          <VStack
            className="peaks-account-panel pd-detail__panel"
            id="account-detail-security-panel"
            gap={4}
            role="tabpanel"
            >
            <Heading level={2}>{t("Sign-in & authenticator")}</Heading>
            <List className="peaks-dense-list" density="balanced" hasDividers>
              <ListItem
                label={t("Riot session")}
                description={(account.canConnectQr ?? account.connected) ? t("Ready to connect through a Riot QR code.") : t("Sign in to Riot again to reconnect this account.")}
                startContent={<Icon color="secondary" icon={Radio} />}
                endContent={<Text type="supporting">{connectionLabel}</Text>}
              />
              <ListItem
                label={t("Authenticator")}
                description={account.hasTotp ? t("Copy a one-time code from the account actions menu.") : t("No authenticator is saved for this account.")}
                startContent={<Icon color="secondary" icon={KeyRound} />}
                endContent={<Text type="supporting">{account.hasTotp ? t("Available") : t("Not configured")}</Text>}
              />
            </List>
          </VStack>
        ) : null}
          </VStack>
        </Grid>
        </VStack>
      </AuthenticatedScreen>
      <AlertDialog
        actionLabel={t("Delete account")}
        description={t("This permanently removes {{value1}}, its saved ranks and matches, and every encrypted secret stored for it on this device.", {value1: displayName(account.riotId)})}
        isActionLoading={isDeleting}
        isOpen={isDeleteOpen}
        onAction={() => void deleteAccount()}
        onOpenChange={isOpen => !isDeleting && setDeleteOpen(isOpen)}
        title={t("Delete this account?")}
      />
      <PasteQrDialog
        accountRiotId={account.riotId}
        isOpen={isPasteQrOpen}
        onConnect={onPasteQr}
        onOpenChange={setPasteQrOpen}
      />
    </>
  )
}
