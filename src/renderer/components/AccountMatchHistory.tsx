import {ChevronRight, History} from 'lucide-react'
import {knownValorantMapAsset, valorantMapName} from '../assets'
import {displayText, t, useLocale} from '../i18n'
import {matchHistoryRow, type MatchHistoryRow} from '../matchHistoryRow'
import {gameProfileIcon} from '../profileAssets'
import {gameMode} from '../riotProfile'
import type {Account, Game, Match} from '../types'
import {EmptyState, Icon, VisuallyHidden} from '../ui'
import {AccountRankEmblem} from './AccountRankEmblem'

function MatchOutcome({row, game}: {row: MatchHistoryRow; game: Game}) {
  const result = row.result === 'Unknown' ? undefined : t(row.result)
  const rounds = game === 'VALORANT' ? row.score?.match(/^(\d+)-(\d+)$/) : undefined
  const placement = row.placement
  const score = placement != null ? `#${placement}` : row.score
  if (!score) return <span className="account-outcome" data-result={row.result}>{result ?? '—'}</span>

  // A surrender can contradict the round count. A League K/D/A never proves a win.
  const winnerByScore = rounds ? Number(rounds[1]) - Number(rounds[2]) : undefined
  const scoreExplainsResult = placement != null || (winnerByScore != null && row.result ===
    (winnerByScore === 0 ? 'Draw' : winnerByScore > 0 ? 'Victory' : 'Defeat'))
  return <span className="account-outcome" data-result={row.result} title={result}>
    {rounds ? <span className="account-outcome__rounds"><b>{rounds[1]}</b><i>:</i><b>{rounds[2]}</b></span>
      : <b className="account-outcome__value">{score}</b>}
    {result && (scoreExplainsResult ? <VisuallyHidden>{result}</VisuallyHidden> : <small>{result}</small>)}
  </span>
}

export function AccountMatchHistory({account, onSelect}: {account: Account; onSelect: (match: Match) => void}) {
  useLocale()
  if (!account.matches?.length) return <EmptyState title={t('No recent matches')} icon={<Icon icon={History} color="secondary" />} />
  // Stable sort keeps the source order for undated legacy entries.
  const matches = [...account.matches].sort((a, b) => (b.playedAtTimestamp ?? 0) - (a.playedAtTimestamp ?? 0))
  return <ol className="account-history" aria-label={t('Match history')}>
    {matches.map((match, index) => {
      const row = matchHistoryRow(match, account.riotId)
      const mode = displayText(gameMode(match))
      const map = match.map && !/^(unknown( map)?|current match)$/i.test(match.map)
        ? match.game === 'VALORANT' ? valorantMapName(match.map) : match.map : undefined
      const title = map || match.game
      const mapArt = match.game === 'VALORANT' && map ? knownValorantMapAsset(map) : undefined
      const art = mapArt ?? row.character?.image
      const details = [row.character?.name, mode !== t('Unknown queue') && !/^\d+$/.test(mode) && mode !== title ? mode : null].filter(Boolean).join(' · ')
      return <li key={match.id ?? index}>
        <button className="account-history__open" type="button" data-result={row.result} onClick={() => onSelect(match)}>
          <span className="account-history__media" data-art={Boolean(art)}>
            <img src={art ?? gameProfileIcon(match.game)} alt={art ? '' : match.game} loading="lazy" />
            {art && <img className="account-history__game" src={gameProfileIcon(match.game)} alt={match.game} />}
          </span>
          <span className="account-history__match"><strong>{title}</strong>{details && <small>{details}</small>}</span>
          <MatchOutcome row={row} game={match.game} />
          <span className="account-history__rating">
            <AccountRankEmblem game={match.game} rank={row.rank} tierId={row.rankTier} />
            {row.delta != null && <b data-direction={Math.sign(row.delta)}>{row.delta > 0 ? '+' : ''}{row.delta} <small>{row.deltaUnit}</small></b>}
          </span>
          <span className="account-history__when">{match.playedAt && displayText(match.playedAt)}{match.duration && <small>{match.duration}</small>}</span>
          <Icon icon={ChevronRight} size="sm" color="secondary" />
        </button>
      </li>
    })}
  </ol>
}
