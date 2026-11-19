import {defineTheme} from '@astryxdesign/core/theme'
import {peaksTheme} from './peaks'

import tftSets from '../assets/profiles/tft-sets.json'

export const riot = defineTheme({name: 'peaks-riot-profile', extends: peaksTheme, localTokens: {
  '--color-game-valorant': '#ff6776', '--color-game-league': '#63bacd', '--color-game-tft': '#c4a0f3',
  '--color-activity-heat': '#ff4655',
  '--color-timeline-now': '#4c9fff', '--color-timeline-midnight': '#ffffff',
  '--color-tft-place-1': '#ffffff', '--color-tft-place-2': '#4b4d50',
  '--color-tft-place-3': '#393b3e', '--color-tft-place-4': '#292b2e',
  '--color-tft-place-5': '#1e2022', '--color-tft-place-6': '#131416',
  '--color-tft-place-7': '#090a0c', '--color-tft-place-8': '#000000',
  '--color-tft-place-gold': '#94670d', '--color-tft-place-silver': '#d1d5da', '--color-tft-place-white': '#ffffff',
  '--color-tft-metal-bronze-shadow': '#633819', '--color-tft-metal-bronze-mid': '#b57542',
  '--color-tft-metal-bronze-light': '#dfaf79', '--color-tft-metal-bronze-highlight': '#ffe1b6',
  '--color-tft-metal-gold-shadow': '#68430b', '--color-tft-metal-gold-mid': '#b07d24',
  '--color-tft-metal-gold-light': '#f1d792', '--color-tft-metal-gold-highlight': '#fff3c4',
  '--color-tft-metal-silver-shadow': '#6b7482', '--color-tft-metal-silver-mid': '#bcc6d2',
  '--color-tft-metal-silver-light': '#e9eff6', '--color-tft-metal-silver-highlight': '#ffffff',
  '--color-tft-ap': '#bda0ff', '--color-tft-ad': '#ffa45e', '--color-tft-health': '#90c9a3',
  '--color-tft-armor': '#e3ce91', '--color-tft-mr': '#b6c8f1', '--color-tft-speed': '#e7cf94', '--color-tft-mana': '#7acdeb',
  '--color-tft-card': '#141419',
  ...Object.fromEntries(Object.entries(tftSets.rarityColors).map(([cost, color]) => [`--color-tft-cost-${cost}`, color])),
  '--color-tft-cost-3': '#63b9ff',
}})

// Scoped game palettes live in the theme, never in global CSS overrides.
export const valorant = defineTheme({name: 'peaks-valorant-profile', extends: riot, tokens: {
  '--color-accent': '#ff6776', '--color-accent-muted': '#362029', '--color-text-accent': '#ff8791',
  '--color-icon-accent': '#ff8791', '--color-on-accent': '#1a0f14',
  '--color-background-surface': '#131116', '--color-background-muted': '#211a22',
}})
export const league = defineTheme({name: 'peaks-league-profile', extends: riot, tokens: {
  '--color-accent': '#d4bb7c', '--color-accent-muted': '#18333b', '--color-text-accent': '#e0c993',
  '--color-icon-accent': '#e0c993', '--color-on-accent': '#101d24',
  '--color-background-surface': '#0c1820', '--color-background-muted': '#172b35',
}})
export const tft = defineTheme({name: 'peaks-tft-profile', extends: riot, tokens: {
  '--color-accent': '#c4a0f3', '--color-accent-muted': '#322345', '--color-text-accent': '#dcc0ff',
  '--color-icon-accent': '#dcc0ff', '--color-on-accent': '#1c1329',
  '--color-background-surface': '#161221', '--color-background-muted': '#271f36',
}, localTokens: {
  '--color-tft-streak-fire': '#ff4723', '--color-tft-streak-ember': '#ffa335', '--color-tft-streak-core': '#fff3b2',
  '--color-tft-streak-ice': '#91dfff', '--color-tft-streak-frost': '#ebfaff',
}})
