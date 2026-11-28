import {ArrowUpRight, Clock3, Share2, X} from 'lucide-react'
import {profilePlayer} from '../accountProfile'
import {gameArtwork, knownValorantMapAsset, valorantAgentName, valorantAgentPortraitAsset, valorantMapName} from '../assets'
import {displayText, t, useLocale} from '../i18n'
import {matchHistoryRow} from '../matchHistoryRow'
import {statsRows} from '../matchStatRows'
import type {PostMatchReview} from '../postMatch'
import {championArtwork, gameProfileIcon} from '../profileAssets'
import {gameMode} from '../riotProfile'
import {TftBoard} from '../screens/TftAccountProfile'
import {Button, Dialog, HStack, Icon, IconButton, VisuallyHidden} from '../ui'
import {AccountRankEmblem} from './AccountRankEmblem'
import {usePlayerPrivacy} from './PlayerPrivacy'
import './postMatchRecap.css'

interface PostMatchReviewDialogProps {
  review: PostMatchReview
  isOpen: boolean
  onDismiss: () => void
  onOpenReport: () => void
  onShare: () => void
}

export function PostMatchReviewDialog({review, isOpen, onDismiss, onOpenReport, onShare}: PostMatchReviewDialogProps) {
  useLocale()
  const {displayName} = usePlayerPrivacy()
  const {account, match} = review
  const isValorant = match.game === 'VALORANT'
  const isTft = match.game === 'Teamfight Tactics'
  const player = profilePlayer(match, account.riotId)
  const hasRoster = match.teams?.some(team => team.players.length)
  const row = matchHistoryRow(match, hasRoster ? player?.riotId ?? player?.name ?? account.riotId : undefined)
  const character = player?.agent || (!hasRoster ? match.agent : undefined)
  const portrait = isValorant ? valorantAgentPortraitAsset(character) : undefined
  const landscape = isValorant ? knownValorantMapAsset(match.map) : isTft ? gameArtwork(match.game) : championArtwork(character) ?? gameArtwork(match.game)
  const map = match.map && !/^(unknown( map)?|current set|current match)$/i.test(match.map)
    ? displayText(isValorant ? valorantMapName(match.map) : match.map) : undefined
  const mode = gameMode(match)
  const caption = [map, mode !== 'Unknown queue' && !/^\d+$/.test(mode) ? displayText(mode) : undefined].filter(Boolean).join(' · ')
  const seconds = match.durationSeconds
  const duration = match.duration || (seconds != null && Number.isFinite(seconds) && seconds > 0 ? `${Math.floor(seconds / 60)}:${String(Math.floor(seconds % 60)).padStart(2, '0')}` : undefined)
  const rounds = isValorant ? row.score?.split('-').map(Number) : undefined
  const byScore = rounds && (rounds[0] === rounds[1] ? 'Draw' : rounds[0] > rounds[1] ? 'Victory' : 'Defeat')
  const verdict = row.result !== 'Unknown' ? t(row.result) : undefined
  const fallback = !verdict && match.result && !/^(unknown|recent match|placement)$/i.test(match.result) ? displayText(match.result) : t('Match complete')
  const stats = statsRows(undefined, player?.stats)
  const metrics = (isTft ? ['Level', 'Eliminations', 'Gold'] : isValorant ? ['ACS', 'ADR', 'HS%', 'Score'] : ['CS', 'Gold'])
    .flatMap(label => {
      const stat = stats.find(value => value.label === label)
      return stat && stat.match !== '—' ? [{label: t(label), value: stat.match}] : []
    })
  const counts = [player?.stats?.kills, player?.stats?.deaths, player?.stats?.assists]
  const kda = counts.every(value => value != null && Number.isSafeInteger(value) && value >= 0)
    ? counts.join(' / ') : player?.score?.match(/^\s*\d+\s*\/\s*\d+\s*\/\s*\d+\s*$/)?.[0]
  if (!isTft && kda) metrics.unshift({label: 'K/D/A', value: kda})
  if (isTft && player?.stats?.damage != null && Number.isFinite(player.stats.damage)) metrics.push({label: t('Damage to players'), value: String(player.stats.damage)})
  const board = isTft ? player?.composition : undefined
  const hasBoard = Boolean(board?.units?.length || board?.augments?.length || board?.traits?.some(trait => trait.tier > 0))

  return <Dialog className="match-recap" label={t('Match recap')} isOpen={isOpen} onOpenChange={open => { if (!open) onDismiss() }}
    padding={0} maxHeight="calc(100dvh - var(--spacing-8))" width="min(92vw, calc(var(--spacing-12) * 21))">
    <article className="match-recap__sheet" data-game={match.game} data-result={row.result}>
      <header className="match-recap__scene">
        {landscape && <img className="match-recap__landscape" src={landscape} alt="" />}
        {portrait && <img className="match-recap__agent" src={portrait} alt={valorantAgentName(character)} />}
        <HStack className="match-recap__top" align="center" gap={3}>
          <img src={gameProfileIcon(match.game)} alt={match.game} />
          {caption && <span>{caption}</span>}
          <IconButton className="match-recap__close" variant="ghost" label={t('Close')} icon={<Icon icon={X} />} onClick={onDismiss} />
        </HStack>
        <div className="match-recap__stage">
          <section className="match-recap__finish">
            <h2 className="match-recap__outcome" data-numeric={Boolean(rounds || row.placement) || undefined}>
              {rounds ? <><VisuallyHidden>{t('Final score')} </VisuallyHidden><b>{rounds[0]}</b><i>:</i><b>{rounds[1]}</b></>
                : row.placement ? <><VisuallyHidden>{t('Placement')} </VisuallyHidden><i>#</i><b>{row.placement}</b></>
                : verdict ?? fallback}
            </h2>
            {rounds && verdict && byScore !== row.result && <strong>{verdict}</strong>}
            <HStack className="match-recap__signature" gap={3} align="center" wrap>
              <bdi>{displayName(account.riotId)}</bdi>
              {duration && <span title={t('Duration')}><Icon icon={Clock3} size="sm" /> {duration}</span>}
            </HStack>
          </section>
          {hasBoard && <section className="match-recap__board"><TftBoard compact composition={board} /></section>}
        </div>
      </header>
      {Boolean(metrics.length || row.rank || row.rankTier || row.delta != null) && <section className="match-recap__performance">
        {metrics.length > 0 && <dl>{metrics.map(metric => <div key={metric.label}><dt>{metric.label}</dt><dd>{metric.value}</dd></div>)}</dl>}
        {(row.rank || row.rankTier || row.delta != null) && <HStack className="match-recap__rating" align="center" gap={2}>
          <AccountRankEmblem game={match.game} rank={row.rank} tierId={row.rankTier} />
          {row.delta != null && <b data-direction={Math.sign(row.delta)}>{row.delta > 0 ? '+' : ''}{row.delta} <small>{row.deltaUnit}</small></b>}
        </HStack>}
      </section>}
      <footer className="match-recap__footer">
        <IconButton variant="ghost" label={t('Share this match')} icon={<Icon icon={Share2} />} onClick={onShare} />
        <Button variant="primary" label={t('Full match report')} endContent={<Icon icon={ArrowUpRight} size="sm" />} onClick={onOpenReport} />
      </footer>
    </article>
  </Dialog>
}
