import {accountRegionLabels} from '../accountRegions'
import {t, useLocale, displayText} from '../i18n'
import {usePlayerPrivacy} from '../components/PlayerPrivacy'
import {useState} from 'react'
import {AlertDialog, List, ListItem} from '../ui'
import {Avatar, Badge, Button as AntButton, Card, Col, Descriptions, Dropdown, Flex, Row, Space, Spin, Tabs, Tag, Tooltip, Typography, type MenuProps} from 'antd'
import {ArrowLeft, BarChart3, Copy, Ellipsis, History, KeyRound, MapPin, QrCode, Radio, RefreshCw, ShieldCheck, Star, Swords, Trash2, Trophy} from 'lucide-react'
import {gameProfileIcon} from '../profileAssets'
import {valorantMapName} from '../assets'
import {CompetitiveInsights} from '../components/CompetitiveInsights'
import {PasteQrDialog} from '../components/PasteQrDialog'
import type {QrImageRequest} from '../qrImage'
import type {Account, Match} from '../types'
import {AuthenticatedScreen, GAMES, MatchList, RankMedia, rankLabel, rankRatingLabel} from './shared'

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

  const canQr = account.canConnectQr ?? account.connected
  const iconButton = (label: string, Glyph: typeof RefreshCw, onClick: () => void) =>
    <Tooltip title={label}><AntButton type="text" icon={<Glyph size={18} />} aria-label={label} onClick={onClick} /></Tooltip>
  const menu: MenuProps['items'] = [
    ...(canQr ? [{key: 'paste-qr', icon: <QrCode size={16} />, label: t('Paste a QR'), onClick: () => setPasteQrOpen(true)}] : []),
    {key: 'enable-mfa', icon: <ShieldCheck size={16} />, label: account.hasTotp ? t('Authenticator saved') : t('Enable MFA'),
      disabled: Boolean(account.hasTotp) || account.owned === false, onClick: () => { void onEnableMfa().catch(() => undefined) }},
    {key: 'copy-totp', icon: <Copy size={16} />, label: t('Copy authenticator code'), disabled: !account.hasTotp, onClick: () => { void onCopy() }},
    {type: 'divider'},
    {key: 'delete-account', icon: <Trash2 size={16} />, label: t('Delete account'), danger: true, onClick: () => setDeleteOpen(true)},
  ]
  const lastPlayed = latestMatch ? (latestMatch.game === 'VALORANT' ? valorantMapName(latestMatch.map) : latestMatch.map ?? latestMatch.game) : undefined

  return (
    <>
      <AuthenticatedScreen screen="account-detail" title={t("Account details")}
        heading={<Flex gap={12} align="center">
          {iconButton(t("All accounts"), ArrowLeft, onBack)}
          <Avatar size={32}>{displayName(account.riotId).slice(0, 1).toUpperCase()}</Avatar>
          <Typography.Title level={3} className="peaks-screen__title">{displayName(account.riotId)}</Typography.Title>
          <Tooltip title={connectionLabel}><Badge status={account.connected ? 'success' : 'warning'} /></Tooltip>
        </Flex>}
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
        <Row gutter={[16, 16]} className="pd-detail">
          <Col xs={24} lg={8}>
            <Flex vertical gap={16}>
              <Card size="small">
                <Descriptions column={1} size="small" colon={false} items={[
                  {key: 'region', label: <Flex gap={8} align="center"><MapPin size={14} />{t('Region')}</Flex>,
                    children: <Flex gap={4} wrap>{accountRegionLabels(account).map(label => <Tag key={label}>{label}</Tag>)}</Flex>},
                  {key: 'level', label: <Flex gap={8} align="center"><Star size={14} />{t('Level')}</Flex>, children: account.level ?? '—'},
                  {key: 'matches', label: <Flex gap={8} align="center"><Swords size={14} />{t('Matches')}</Flex>, children: account.matches?.length ?? 0},
                  {key: 'last', label: <Flex gap={8} align="center"><History size={14} />{t('Last played')}</Flex>,
                    children: lastPlayed ? <Flex vertical><span>{lastPlayed}</span>{latestMatch?.playedAt ? <Typography.Text type="secondary">{displayText(latestMatch.playedAt)}</Typography.Text> : null}</Flex> : t('No matches yet')},
                  {key: 'synced', label: <Flex gap={8} align="center"><RefreshCw size={14} />{t('Synced')}</Flex>, children: displayText(account.lastUpdated ?? 'Last synced just now')},
                ]} />
              </Card>
              <Card size="small" title={<Flex gap={8} align="center"><Trophy size={16} />{t("Ranks")}</Flex>} styles={{body: {padding: 4}}}>
                <List className="pd-detail__rank-list" density="balanced" hasDividers>
                  {GAMES.map(game => {
                    const rank = account.ranks.find(item => item.game === game)
                    return <ListItem key={game} label={displayText(rankLabel(rank))}
                      startContent={<Tooltip title={game}><img className="pd-riot-game-icon pd-riot-game-icon--small" src={gameProfileIcon(game)} alt={game} /></Tooltip>}
                      endContent={<Flex gap={8} align="center">{rank?.rating != null ? <Typography.Text type="secondary">{rankRatingLabel(game, rank.rating)}</Typography.Text> : null}<RankMedia rank={rank} /></Flex>} />
                  })}
                </List>
              </Card>
            </Flex>
          </Col>
          <Col xs={24} lg={16}>
            <Card size="small" className="pd-detail__main">
              <Tabs activeKey={tab} onChange={value => setTab(value as AccountTab)} items={[
                {key: 'matches', icon: <History size={16} />, label: t("Matches"),
                  children: <MatchList riotId={account.riotId} matches={account.matches ?? []} onSelect={onSelectMatch} />},
                {key: 'insights', icon: <BarChart3 size={16} />, label: t("Insights"),
                  children: <CompetitiveInsights matches={account.matches ?? []} riotId={account.riotId} />},
                {key: 'security', icon: <ShieldCheck size={16} />, label: t("Security"), children: <Descriptions column={1} size="small" items={[
                  {key: 'session', label: <Flex gap={8} align="center"><Radio size={14} />{t("Riot session")}</Flex>,
                    children: <Badge status={account.connected ? 'success' : 'warning'} text={canQr ? t("Ready to connect through a Riot QR code.") : t("Sign in to Riot again to reconnect this account.")} />},
                  {key: 'totp', label: <Flex gap={8} align="center"><KeyRound size={14} />{t("Authenticator")}</Flex>,
                    children: <Badge status={account.hasTotp ? 'success' : 'default'} text={account.hasTotp ? t("Available") : t("Not configured")} />},
                ]} />},
              ]} />
            </Card>
          </Col>
        </Row>
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
