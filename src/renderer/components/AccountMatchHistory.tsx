import {Check, ChevronRight, Equal, History, X} from 'lucide-react'
import {valorantMapName} from '../assets'
import {displayText, t, useLocale} from '../i18n'
import {matchHistoryRow} from '../matchHistoryRow'
import {gameProfileIcon} from '../profileAssets'
import {gameMode} from '../riotProfile'
import type {Account, Match} from '../types'
import {EmptyState, HStack, Icon, Tooltip, VisuallyHidden, VStack} from '../ui'

export function AccountMatchHistory({account, onSelect}: {account: Account; onSelect: (match: Match) => void}) {
  useLocale()
  if (!account.matches?.length) return <EmptyState title={t('No recent matches')} icon={<Icon icon={History} color="secondary" />} />
  // Legacy entries without a timestamp keep their provider order after dated games.
  const matches = [...account.matches].sort((left, right) => (right.playedAtTimestamp ?? 0) - (left.playedAtTimestamp ?? 0))
  return <table className="account-history" aria-label={t('Match history')}>
    <thead><tr>
      <th scope="col"><VisuallyHidden>{t('Match')}</VisuallyHidden></th><th scope="col">{t('Result')}</th><th scope="col">{t('Score')}</th>
      <th scope="col">{t('Rank')}</th><th scope="col">{t('Played')}</th>
    </tr></thead>
    <tbody>{matches.map((match, index) => {
      const row = matchHistoryRow(match, account.riotId)
      const mode = displayText(gameMode(match))
      const map = match.map && !/^(unknown( map)?|current match)$/i.test(match.map)
        ? match.game === 'VALORANT' ? valorantMapName(match.map) : match.map : undefined
      const title = map || match.game
      const details = [row.character?.name, mode !== t('Unknown queue') && !/^\d+$/.test(mode) && mode !== title ? mode : null].filter(Boolean).join(' · ')
      const score = row.placement != null ? `#${row.placement}` : row.score ?? '—'
      const delta = row.delta != null ? `${row.delta > 0 ? '+' : ''}${row.delta} ${row.deltaUnit ?? ''}`.trim() : undefined
      return <tr key={match.id ?? index} onClick={() => onSelect(match)}>
        <th scope="row">
          <button className="account-history__open" type="button" onClick={event => { event.stopPropagation(); onSelect(match) }}>
            <span className="account-history__media">
              <img src={row.character?.image ?? gameProfileIcon(match.game)} alt={match.game} />
              {row.character ? <img className="account-history__game" src={gameProfileIcon(match.game)} alt="" /> : null}
            </span>
            <VStack as="span" className="account-history__match" gap={0.5}>
              <strong>{title}</strong>{details ? <small>{details}</small> : null}
            </VStack>
          </button>
        </th>
        <td>{row.result === 'Unknown' ? '—' : <Tooltip content={t(row.result)}>
          <span className="account-history__result" data-result={row.result}><Icon icon={row.result === 'Victory' ? Check : row.result === 'Defeat' ? X : Equal} label={t(row.result)} /></span>
        </Tooltip>}</td>
        <td className="account-history__score">{score}</td>
        <td><HStack as="span" className="account-history__rating" align="center" gap={2} wrap>
          {row.rank ? <span>{displayText(row.rank)}</span> : null}
          {delta ? <b data-result={row.delta! > 0 ? 'Victory' : row.delta! < 0 ? 'Defeat' : undefined}>{delta}</b> : null}
          {!delta && !row.rank ? '—' : null}
        </HStack></td>
        <td><HStack as="span" justify="between" align="center" gap={1}>
          <VStack as="span">{match.playedAt ? displayText(match.playedAt) : '—'}{match.duration ? <small>{match.duration}</small> : null}</VStack>
          <Icon icon={ChevronRight} size="sm" color="secondary" />
        </HStack></td>
      </tr>
    })}</tbody>
  </table>
}
