import type {PeaksTheme} from '../ui'
import type {ProfileGame} from '../riotProfile'

/** Each game's profile keeps its own accent (see theme/tokens.css and ui/theme.tsx). */
export const profileTheme = (game: ProfileGame): PeaksTheme =>
  game === 'VALORANT' ? 'valorant' : game === 'League of Legends' ? 'league' : game === 'Teamfight Tactics' ? 'tft' : 'riot'
