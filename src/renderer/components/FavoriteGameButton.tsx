import {useRef, useState} from 'react'
import {Button, ButtonGroup, Divider, DropdownMenu, DropdownMenuItem, HStack, Icon, useToast, VisuallyHidden} from '../ui'
import {ChevronDown} from 'lucide-react'
import {invoke} from '../bridge'
import {displayText, t, useLocale} from '../i18n'
import {gameProfileIcon} from '../profileAssets'
import type {AppState, Game} from '../types'

const games: readonly Game[] = ['VALORANT', 'League of Legends', 'Teamfight Tactics']
const gameIcon = (game: Game) => <img src={gameProfileIcon(game)} alt=""
  style={{width: 'var(--spacing-6)', height: 'var(--spacing-6)', objectFit: 'contain'}} />

export function FavoriteGameButton({state, onStateChange, onSignInRequired}: {
  state: AppState
  onStateChange: (state: AppState) => void
  /** Called instead of launching when no Riot account is signed in. */
  onSignInRequired: () => void
}) {
  useLocale()
  const showToast = useToast()
  const [pending, setPending] = useState<'save' | 'launch' | null>(null)
  const inFlight = useRef(false)
  const favorite = state.settings.favoriteGame ?? 'VALORANT'

  const perform = async (kind: 'save' | 'launch', game?: string) => {
    if (inFlight.current || (kind === 'save' && game === favorite)) return
    // Launching without a signed-in account would only open Riot's login
    // screen; send the user to Accounts so they can connect one first.
    if (kind === 'launch' && !state.activeAccountId) {
      onSignInRequired()
      return
    }
    inFlight.current = true
    setPending(kind)
    try {
      const next = await invoke<AppState>(kind === 'save' ? 'settings' : 'launch_favorite_game',
        kind === 'save' ? {favoriteGame: game} : {})
      onStateChange(next)
      if (next.operationNotice) showToast({body: displayText(next.operationNotice), type: 'info', uniqueID: 'favorite-game'})
    } catch (error) {
      showToast({body: displayText(error instanceof Error ? error.message : 'That action could not be completed'),
        type: 'error', uniqueID: 'favorite-game', isAutoHide: true})
    } finally {
      inFlight.current = false
      setPending(null)
    }
  }

  return <ButtonGroup label={t('Favorite game')} size="md">
    <Button label={t('Launch {{game}}', {game: favorite})} tooltip={t('Launch {{game}}', {game: favorite})}
      icon={gameIcon(favorite)} isIconOnly variant="ghost" style={{backgroundImage: 'none'}}
      isLoading={pending === 'launch'} isDisabled={pending === 'save'} clickAction={() => perform('launch')} />
    <Divider orientation="vertical" variant="strong" aria-hidden="true"
      style={{height: 'var(--spacing-6)', alignSelf: 'center'}} />
    <DropdownMenu presentation="popover" alignment="end" hasChevron={false}
      menuWidth="max-content"
      button={{label: t('Choose favorite game'), tooltip: t('Choose favorite game'), isIconOnly: true,
        icon: <Icon icon={ChevronDown} size="sm" />, variant: 'ghost',
        style: {backgroundImage: 'none', borderInlineStart: 'none'}, isDisabled: pending !== null}}>
      {games.map(game => <DropdownMenuItem key={game}
        label={<HStack justify="center" align="center">
          {gameIcon(game)}
          <VisuallyHidden>{game === favorite ? `${game} · ${t('Favorite game')}` : game}</VisuallyHidden>
        </HStack>}
        onClick={() => { void perform('save', game) }} isDisabled={pending !== null}
        style={game === favorite ? {backgroundColor: 'var(--color-overlay-pressed)'} : undefined} />)}
    </DropdownMenu>
  </ButtonGroup>
}
