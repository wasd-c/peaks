import {Button, FullscreenOverlay} from '../ui'
import {t, useLocale} from '../i18n'
import {gameArtwork} from '../assets'
import {gameProfileIcon} from '../profileAssets'
import type {Game} from '../types'

const games: readonly Game[] = ['VALORANT', 'League of Legends', 'Teamfight Tactics']

/** Asked before an account is used: which game to launch, or (corner close) none. */
export function GameChooser({isOpen, onChoose, onCancel}: {
  isOpen: boolean
  /** `null` when the chooser is dismissed: use the account without launching a game. */
  onChoose: (game: Game | null) => void
  /** Abandon using the account altogether. */
  onCancel: () => void
}) {
  useLocale()
  return <FullscreenOverlay isOpen={isOpen} onClose={() => onChoose(null)}
    label={t('Choose a game to launch')} closeLabel={t('Do not launch a game')} closeText={t('Skip')}>
    <div className="pd-game-chooser-layout">
    <div className="pd-game-chooser">
      {games.map(game => <Button key={game} className="pd-game-chooser__game" variant="ghost"
        label={t('Launch {{game}}', {game})} onClick={() => onChoose(game)} hasTooltip={false}>
        <img className="pd-game-chooser__art" src={gameArtwork(game)} alt="" />
        <img className="pd-game-chooser__logo" src={gameProfileIcon(game)} alt="" />
        <span className="pd-game-chooser__name">{game}</span>
      </Button>)}
    </div>
    <Button label={t('Cancel')} variant="secondary" size="lg" onClick={onCancel} />
    </div>
  </FullscreenOverlay>
}
