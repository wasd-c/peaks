import {t, useLocale} from '../i18n'
import {useState} from 'react'
import {Badge, Button, Empty, Flex, Input, Typography} from 'antd'
import {Search, Star} from 'lucide-react'
import {usePlayerPrivacy} from '../components/PlayerPrivacy'
import type {AppState, Player} from '../types'
import {AuthenticatedScreen, PlayerList, type ActionCallback} from './shared'

export interface WatchlistScreenProps {
  state: AppState
  action: ActionCallback
  onSelectPlayer: (player: Player) => void
}

export function WatchlistScreen({state, action, onSelectPlayer}: WatchlistScreenProps) {
  useLocale()
  const {displayName} = usePlayerPrivacy()
  const [query, setQuery] = useState('')
  const players = state.followed.filter(player => (
    displayName(player.riotId).toLocaleLowerCase().includes(query.trim().toLocaleLowerCase())
  ))
  const count = state.followed.length
  return (
    <AuthenticatedScreen screen="watchlist" title={t("Watchlist")}
      heading={<Flex gap={12} align="center">
        <Typography.Title level={3} className="peaks-screen__title">{t("Watchlist")}</Typography.Title>
        {count ? <Badge count={count} color="var(--color-background-muted)" style={{color: 'var(--color-text-secondary)', boxShadow: 'none'}} /> : null}
      </Flex>}
      actions={count ? <Input allowClear prefix={<Search size={14} aria-hidden />} placeholder={t("Find a watched player")} aria-label={t("Filter watched players")}
        value={query} onChange={event => setQuery(event.target.value)} style={{width: 240}} /> : null}>
      <Flex vertical gap={16} className="pd-watch">
        {count === 0 ? <Empty image={<Star size={40} aria-hidden />} description={t("Find a player in Search, then select Watch to add them here.")} />
          : players.length ? <PlayerList action={action} onSelect={onSelectPlayer} players={players.map(player => ({...player, followed: true}))} />
          : <Empty image={<Search size={40} aria-hidden />} description={t("No players found")}><Button onClick={() => setQuery('')}>{t("Clear search")}</Button></Empty>}
      </Flex>
    </AuthenticatedScreen>
  )
}

/** Compatibility export while callers migrate to WatchlistScreen. */
export const FollowedScreen = WatchlistScreen
export type FollowedScreenProps = WatchlistScreenProps
