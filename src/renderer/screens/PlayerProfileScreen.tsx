import {Button, HStack, Icon, List, ListItem, Text, VStack} from '../ui'
import {ArrowLeft, Star} from 'lucide-react'
import {valorantMapName} from '../assets'
import {ChartSection} from '../components/RiotActivity'
import {displayText, localeTags, t, useLocale} from '../i18n'
import {mergeRiotProfile} from '../playerProfiles'
import type {Match, Player, PlayerStats} from '../types'
import {AccountScreen} from './AccountScreen'

export interface PlayerProfileScreenProps {
  player: Player
  isLoading?: boolean
  watched?: boolean
  followed?: boolean
  onBack: () => void
  onSelectMatch: (match: Match) => void
  onRefresh?: () => Promise<void>
  onToggleWatchlist?: () => void | Promise<void>
  onToggleFollow?: () => void | Promise<void>
}

const STAT_LABELS: Array<[keyof PlayerStats, string]> = [
  ['kills', 'Kills'], ['deaths', 'Deaths'], ['assists', 'Assists'], ['combatScore', 'Combat score'],
  ['damage', 'Damage'], ['headshots', 'Headshots'], ['gold', 'Gold'], ['minions', 'CS'],
  ['vision', 'Vision score'], ['level', 'Level'], ['placement', 'Placement'], ['playersEliminated', 'Players eliminated'],
]

export function PlayerProfileScreen({player, isLoading = false, watched, followed, onBack, onSelectMatch, onRefresh, onToggleWatchlist, onToggleFollow}: PlayerProfileScreenProps) {
  const locale = useLocale()
  const profile = mergeRiotProfile(player, [], [])
  const isWatched = watched ?? followed ?? false
  const toggle = onToggleWatchlist ?? onToggleFollow
  const stats = player.context?.stats ?? {}
  const contextMap = player.game === 'VALORANT' && player.context?.map ? valorantMapName(player.context.map) : player.context?.map
  return <AccountScreen account={{...profile, ranks: profile.ranks ?? [], owned: false}} owned={false} isActive={false}
    isSynchronizing={isLoading} activity={profile.activity} onRefresh={onRefresh} onSelectMatch={onSelectMatch}
    actions={<HStack gap={2}>
      <Button label={t('Back')} variant="ghost" icon={<Icon icon={ArrowLeft} />} onClick={onBack} />
      <Button label={t(isWatched ? 'Unwatch' : 'Watch')} variant={isWatched ? 'secondary' : 'primary'} icon={<Icon icon={Star} />} clickAction={async () => { await toggle?.() }} />
    </HStack>}
    contextContent={<VStack gap={4}>
      {profile.cachedAt ? <Text color="secondary" type="supporting">{t('Saved profile · last fetched {{date}}', {date: new Intl.DateTimeFormat(localeTags[locale], {dateStyle: 'medium', timeStyle: 'short'}).format(profile.cachedAt)})}</Text> : null}
      {player.context ? <ChartSection title={t('Match performance')} detail={displayText(player.context.label)}>
        <List density="compact" hasDividers>
          <ListItem label={displayText(contextMap ?? player.context.label)} description={displayText(player.context.character ?? 'Character unavailable')} endContent={<Text>{player.context.score ?? '—'}</Text>} />
          {STAT_LABELS.flatMap(([key, label]) => stats[key] == null || typeof stats[key] !== 'number' ? [] : [<ListItem key={key} label={t(label)} endContent={<Text hasTabularNumbers>{stats[key].toLocaleString()}</Text>} />])}
        </List>
      </ChartSection> : null}
    </VStack>} />
}
