import {accountRegionLabels} from '../accountRegions'
import {t, useLocale, displayText} from '../i18n'
import {usePlayerPrivacy} from '../components/PlayerPrivacy'
import {useState} from 'react'
import {AlertDialog, Avatar, HStack, Icon, Text, VisuallyHidden, VStack} from '../ui'
import {Badge, Button as AntButton, Descriptions, Dropdown, Flex, Space, Spin, Tabs, Tooltip, Typography, type MenuProps} from 'antd'
import {ArrowLeft, BarChart3, Copy, Ellipsis, History, KeyRound, QrCode, Radio, RefreshCw, ShieldCheck, Trash2} from 'lucide-react'
import {gameProfileIcon} from '../profileAssets'
import {resolveAccountIcon} from '../accountIcons'
import {AccountRankEmblem} from '../components/AccountRankEmblem'
import {AccountMatchHistory} from '../components/AccountMatchHistory'
import './accountDetail.css'
import {CompetitiveInsights} from '../components/CompetitiveInsights'
import {PasteQrDialog} from '../components/PasteQrDialog'
import type {QrImageRequest} from '../qrImage'
import type {Account, Match} from '../types'
import {AuthenticatedScreen, GAMES, rankLabel, rankRatingLabel} from './shared'

type AccountTab = 'matches' | 'insights' | 'security'

export interface AccountDetailScreenProps {
  account: Account
  onBack: () => void
  onCopy: () => void | Promise<void>
  onConnect: () => void
  onEnableMfa: () => Promise<void>
  isEnablingMfa?: boolean
  onDelete: () => void | Promise<void>
  onPasteQr: (payload: QrImageRequest) => Promise<void>
  onRefresh: () => void | Promise<void>
  onSelectMatch: (match: Match) => void
  onOpenProfile?: () => void
}

export function AccountDetailScreen({
  account,
  onBack,
  onCopy,
  onConnect,
  onEnableMfa,
  isEnablingMfa = false,
  onDelete,
  onPasteQr,
  onRefresh,
  onSelectMatch,
  onOpenProfile,
}: AccountDetailScreenProps) {
  useLocale()
  const {displayName} = usePlayerPrivacy()
  const [tab, setTab] = useState<AccountTab>('matches')
  const [isDeleteOpen, setDeleteOpen] = useState(false)
  const [isDeleting, setDeleting] = useState(false)
  const [isPasteQrOpen, setPasteQrOpen] = useState(false)
  const connectionLabel = account.connected ? t('Connected') : t('Offline')
  const name = displayName(account.riotId)
  const avatar = resolveAccountIcon(account)
  const regions = accountRegionLabels(account)
  const ranks = GAMES.flatMap(game => {
    const rank = account.ranks.find(item => item.game === game)
    return rank?.tier.trim() && !/^(unranked|unknown|unavailable|rank unavailable|—|-)$/i.test(rank.tier.trim()) ? [rank] : []
  })
  const unrankedGames = account.ranks.filter(rank => /^unranked$/i.test(rank.tier.trim()))

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

  const canQr = account.canConnectQr ?? account.connected
  const iconButton = (label: string, Glyph: typeof RefreshCw, onClick: () => void) =>
    <Tooltip title={label}><AntButton type="text" icon={<Glyph size={18} />} aria-label={label} onClick={onClick} /></Tooltip>
  const tabLabel = (label: string, glyph: typeof History, count?: number) => <Tooltip title={label}>
    <HStack as="span" align="center" gap={1.5}><Icon icon={glyph} /><VisuallyHidden>{label}</VisuallyHidden>
      {count != null ? <Badge className="account-detail__count" count={count} showZero overflowCount={9999} /> : null}
    </HStack>
  </Tooltip>
  const menu: MenuProps['items'] = [
    ...(canQr ? [{key: 'paste-qr', icon: <QrCode size={16} />, label: t('Paste a QR'), onClick: () => setPasteQrOpen(true)}] : []),
    {key: 'enable-mfa', icon: <ShieldCheck size={16} />, label: account.hasTotp ? t('Authenticator saved') : t('Enable MFA'),
      disabled: Boolean(account.hasTotp) || account.owned === false, onClick: () => { void onEnableMfa().catch(() => undefined) }},
    {key: 'copy-totp', icon: <Copy size={16} />, label: t('Copy authenticator code'), disabled: !account.hasTotp, onClick: () => { void onCopy() }},
    {type: 'divider'},
    {key: 'delete-account', icon: <Trash2 size={16} />, label: t('Delete account'), danger: true, onClick: () => setDeleteOpen(true)},
  ]
  return (
    <>
      <AuthenticatedScreen screen="account-detail" title={t("Account details")}
        heading={<HStack className="account-detail__identity" align="center" gap={3}>
          {iconButton(t('All accounts'), ArrowLeft, onBack)}
          <Avatar src={avatar?.image} alt="" name={name} size="lg" shape="rounded" tooltip={false} />
          <VStack gap={1}>
            <Typography.Title level={3} className="peaks-screen__title">{name}</Typography.Title>
            <HStack className="account-detail__meta" gap={3} wrap align="center">
              <Tooltip title={connectionLabel}><Badge status={account.connected ? 'success' : 'default'} aria-label={connectionLabel} /></Tooltip>
              {regions.map(region => <Text key={region}>{region}</Text>)}
              {account.level != null ? <Text>{t('Level {{level}}', {level: account.level})}</Text> : null}
            </HStack>
          </VStack>
        </HStack>}
        actions={<>
          {onOpenProfile ? iconButton(t('VALORANT profile'), BarChart3, onOpenProfile) : null}
          {iconButton(t("Refresh account data"), RefreshCw, () => { void onRefresh() })}
          <Space.Compact>
            <AntButton type="primary" icon={<Radio size={16} />} disabled={isEnablingMfa} onClick={onConnect}>
              {canQr ? t("Connect Riot Client") : t("Sign in to Riot again")}
            </AntButton>
            <Dropdown menu={{items: menu}} trigger={['click']} placement="bottomRight" disabled={isEnablingMfa}>
              <AntButton type="primary" aria-label={isEnablingMfa ? t('Enabling MFA…') : t("More Riot account actions")}
                icon={isEnablingMfa ? <Spin size="small" /> : <Ellipsis size={16} />} />
            </Dropdown>
          </Space.Compact>
        </>}>
        <VStack className="account-detail-body" gap={6}>
          <HStack as="section" className="account-rank-strip" aria-label={t('Ranks')} gap={5} align="center" wrap>
            {ranks.length ? ranks.map(rank => {
              const label = rankLabel(rank)
              const rating = rank.rating
              const hasRating = rating != null && Number.isFinite(rating) && rating >= 0
              const showMeter = hasRating && rating <= 100 && rank.game === 'VALORANT'
                && /^(iron|bronze|silver|gold|platinum|diamond|ascendant)\b/i.test(label)
              return <HStack key={rank.game} className="account-rank-strip__game" gap={3} align="center">
                <Tooltip title={rank.game}><img className="account-rank-strip__logo" src={gameProfileIcon(rank.game)} alt={rank.game} /></Tooltip>
                <AccountRankEmblem game={rank.game} rank={label} />
                {hasRating ? <VStack gap={1}>
                  <Text hasTabularNumbers weight="semibold">{rankRatingLabel(rank.game, rating)}</Text>
                  {showMeter ? <meter className="account-rank-strip__meter" min={0} max={100} value={rating} aria-label={rankRatingLabel(rank.game, rating)} /> : null}
                </VStack> : null}
              </HStack>
            }) : <HStack align="center" gap={2}>
              {unrankedGames.map(({game}) => <Tooltip key={game} title={game}><img className="account-rank-strip__logo" src={gameProfileIcon(game)} alt={game} /></Tooltip>)}
              <Text color="secondary">{unrankedGames.length ? t('Unranked') : t('Rank unavailable')}</Text>
            </HStack>}
          </HStack>
          <Tabs className="account-detail-tabs" activeKey={tab} onChange={value => setTab(value as AccountTab)}
            tabBarExtraContent={account.lastUpdated ? <Tooltip title={t('Synced')}><HStack className="account-detail__synced" align="center" gap={1.5}><Icon icon={RefreshCw} size="sm" label={t('Synced')} />{displayText(account.lastUpdated)}</HStack></Tooltip> : undefined}
            items={[
                {key: 'matches', label: tabLabel(t('Matches'), History, account.matches?.length ?? 0),
                  children: <AccountMatchHistory account={account} onSelect={onSelectMatch} />},
                {key: 'insights', label: tabLabel(t('Insights'), BarChart3),
                  children: <CompetitiveInsights matches={account.matches ?? []} riotId={account.riotId} />},
                {key: 'security', label: tabLabel(t('Security'), ShieldCheck), children: <Descriptions column={1} size="small" items={[
                  {key: 'session', label: <Flex gap={8} align="center"><Radio size={14} />{t("Riot session")}</Flex>,
                    children: <Badge status={account.connected ? 'success' : 'warning'} text={canQr ? t("Ready to connect through a Riot QR code.") : t("Sign in to Riot again to reconnect this account.")} />},
                  {key: 'totp', label: <Flex gap={8} align="center"><KeyRound size={14} />{t("Authenticator")}</Flex>,
                    children: <Badge status={account.hasTotp ? 'success' : 'default'} text={account.hasTotp ? t("Available") : t("Not configured")} />},
                ]} />},
              ]} />
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
