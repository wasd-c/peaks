import {peaksRiotProfileTheme as riot} from './peaks-riot-profile'
import {peaksValorantProfileTheme as valorant} from './peaks-valorant-profile'
import {peaksLeagueProfileTheme as league} from './peaks-league-profile'
import {peaksTftProfileTheme as tft} from './peaks-tft-profile'
import type {ProfileGame} from '../riotProfile'

export const profileTheme = (game: ProfileGame) => game === 'VALORANT' ? valorant : game === 'League of Legends' ? league : game === 'Teamfight Tactics' ? tft : riot
