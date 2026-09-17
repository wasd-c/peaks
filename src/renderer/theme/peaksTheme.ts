import {defineSyntaxTheme, defineTheme} from '@astryxdesign/core/theme';
import {neutralTheme} from '@astryxdesign/theme-neutral';

const peaksSyntax = defineSyntaxTheme({
  name: 'peaks-color',
  tokens: {
    keyword: ['#6d28d9', '#c4b5fd'],
    string: ['#15803d', '#86efac'],
    comment: ['#737373', '#8a8a8a'],
    number: ['#b45309', '#fbbf24'],
    function: ['#1d4ed8', '#93c5fd'],
    type: ['#0e7490', '#67e8f9'],
    variable: ['#0a0a0a', '#f5f5f5'],
    operator: ['#be185d', '#f9a8d4'],
    constant: ['#c2410c', '#fdba74'],
    tag: ['#b91c1c', '#fca5a5'],
    attribute: ['#a16207', '#fde047'],
    property: ['#0f766e', '#5eead4'],
    punctuation: ['#8a8a8a', '#666666'],
    background: ['#ededed', '#1a1a1a'],
  },
});

// Astryx emits custom properties at build time; keeping the client primitives
// separate preserves strict checking for Astryx's named semantic tokens.
const clientTokens = {
  '--peaks-tracking-label': '0.12em',
  '--peaks-tracking-heading': '-0.03em',
  '--peaks-hero-title-size': 'clamp(2.5rem, 3.8vw, 4.5rem)',
  '--peaks-content-width': '1600px',
  '--peaks-sidebar-width': '80px',
  '--peaks-hero-height': '280px',
  '--peaks-artwork-opacity': '0.72',
  '--peaks-avatar-size': '44px',
  '--peaks-account-column': '240px',
  '--peaks-transition-distance': '8px',
  '--peaks-team-ally': '#164638',
  '--peaks-team-self': '#173f69',
  '--peaks-team-enemy': '#5b2630',
  '--peaks-party-yellow': '#f3cf63',
  '--peaks-party-purple': '#b38bf5',
  '--peaks-party-blue': '#344fc4',
  '--peaks-font-game': '"Bahnschrift", "Arial Narrow", "Segoe UI", sans-serif',
  '--peaks-poster-light': '#637cbc',
} satisfies Record<`--peaks-${string}`, string>;

/**
 * A quiet game-client canvas: warm white controls, precise typography, and
 * restrained semantic feedback leave the VALORANT artwork room to lead.
 */
export const peaksTheme = defineTheme({
  name: 'peaks',
  extends: neutralTheme,

  typography: {
    scale: {base: 14, ratio: 1.22},
    body: {
      family: 'Segoe UI Variable',
      fallbacks:
        '"Segoe UI", -apple-system, BlinkMacSystemFont, Helvetica, Arial, sans-serif',
      weight: 'normal',
    },
    heading: {
      family: 'Segoe UI Variable Display',
      fallbacks: '"Arial Narrow", "Segoe UI", Helvetica, Arial, sans-serif',
      weight: 'bold',
      weights: {1: 'bold', 2: 'bold'},
    },
    code: {
      family: 'Cascadia Mono',
      fallbacks:
        '"SF Mono", Consolas, "Liberation Mono", "Courier New", monospace',
    },
  },

  radius: {base: 4, multiplier: 1.5},
  motion: {
    fast: 140,
    medium: 320,
    slow: 620,
    ratio: 0.75,
    easing: 'cubic-bezier(0.22, 1, 0.36, 1)',
  },

  syntax: peaksSyntax,

  tokens: {
    ...clientTokens,
    // Core canvas and interaction palette.
    '--color-accent': ['#181818', '#ece8e1'],
    '--color-accent-muted': ['#e8e5df', '#292825'],
    '--color-on-accent': ['#faf8f3', '#111111'],
    '--color-neutral': ['#00000012', '#ffffff1a'],
    '--color-background-surface': ['#faf9f6', '#101113'],
    '--color-background-body': ['#f2f0eb', '#08090b'],
    '--color-background-card': ['#faf9f6', '#17181b'],
    '--color-background-popover': ['#faf9f6', '#1b1b1d'],
    '--color-background-muted': ['#e9e7e2', '#1d1d1f'],
    '--color-background-inverted': ['#111111', '#ece8e1'],
    '--color-background-error-inverted': ['#b91c1c', '#fb7185'],
    '--color-overlay': ['#000000a6', '#000000d9'],
    '--color-overlay-hover': ['#0000000a', '#ffffff0d'],
    '--color-overlay-pressed': ['#00000014', '#ffffff1a'],
    '--color-text-primary': ['#181818', '#f0f1f3'],
    '--color-text-secondary': ['#575651', '#a5a8b0'],
    '--color-text-disabled': ['#8a8a8a', '#666666'],
    '--color-text-accent': ['#181818', '#ece8e1'],
    '--color-on-dark': '#ffffff',
    '--color-on-light': '#0a0a0a',
    '--color-icon-accent': ['#181818', '#ece8e1'],
    '--color-icon-primary': ['#181818', '#ece8e1'],
    '--color-icon-secondary': ['#575651', '#9d9b97'],
    '--color-icon-disabled': ['#8a8a8a', '#666666'],

    '--color-success': ['#376b50', '#8ab7a0'],
    '--color-success-muted': ['#e1ece5', '#1b2b23'],
    '--color-on-success': ['#ffffff', '#112319'],
    '--color-error': ['#dc2626', '#fb7185'],
    '--color-error-muted': ['#fee2e2', '#451a24'],
    '--color-on-error': ['#ffffff', '#4c0519'],
    '--color-warning': ['#84621f', '#cfb887'],
    '--color-warning-muted': ['#f2ebdc', '#30291c'],
    '--color-on-warning': ['#ffffff', '#2c2416'],

    '--color-border': ['#1717171a', '#ece8e117'],
    '--color-border-emphasized': ['#86837e', '#656460'],
    '--color-skeleton': ['#dedede', '#333333'],
    '--color-track': ['#c7c7c7', '#404040'],
    '--color-shadow': ['#00000024', '#000000a6'],
    '--color-tint-hover': ['black', 'white'],
    '--focus-outline-color': 'var(--color-accent)',

    // Categorical colors drive rank tiers and compact match-result tokens.
    '--color-background-blue': ['#dbeafe', '#172554'],
    '--color-border-blue': ['#93c5fd', '#1d4ed8'],
    '--color-icon-blue': ['#1d4ed8', '#93c5fd'],
    '--color-text-blue': ['#1e40af', '#bfdbfe'],
    '--color-background-cyan': ['#cffafe', '#164e63'],
    '--color-border-cyan': ['#67e8f9', '#0891b2'],
    '--color-icon-cyan': ['#0e7490', '#67e8f9'],
    '--color-text-cyan': ['#155e75', '#a5f3fc'],
    '--color-background-gray': ['#e0e0e0', '#282828'],
    '--color-border-gray': ['#a3a3a3', '#737373'],
    '--color-icon-gray': ['#171717', '#f5f5f5'],
    '--color-text-gray': ['#171717', '#f5f5f5'],
    '--color-background-green': ['#dcfce7', '#14532d'],
    '--color-border-green': ['#86efac', '#15803d'],
    '--color-icon-green': ['#15803d', '#4ade80'],
    '--color-text-green': ['#166534', '#bbf7d0'],
    '--color-background-orange': ['#ffedd5', '#431407'],
    '--color-border-orange': ['#fdba74', '#c2410c'],
    '--color-icon-orange': ['#c2410c', '#fb923c'],
    '--color-text-orange': ['#9a3412', '#fed7aa'],
    '--color-background-pink': ['#fce7f3', '#500724'],
    '--color-border-pink': ['#f9a8d4', '#be185d'],
    '--color-icon-pink': ['#be185d', '#f472b6'],
    '--color-text-pink': ['#9d174d', '#fbcfe8'],
    '--color-background-purple': ['#ede9fe', '#2e1065'],
    '--color-border-purple': ['#c4b5fd', '#7c3aed'],
    '--color-icon-purple': ['#6d28d9', '#a78bfa'],
    '--color-text-purple': ['#5b21b6', '#ddd6fe'],
    '--color-background-red': ['#fee2e2', '#450a0a'],
    '--color-border-red': ['#fca5a5', '#dc2626'],
    '--color-icon-red': ['#dc2626', '#fb7185'],
    '--color-text-red': ['#b91c1c', '#fecaca'],
    '--color-background-teal': ['#ccfbf1', '#134e4a'],
    '--color-border-teal': ['#5eead4', '#0f766e'],
    '--color-icon-teal': ['#0f766e', '#2dd4bf'],
    '--color-text-teal': ['#115e59', '#99f6e4'],
    '--color-background-yellow': ['#fef9c3', '#422006'],
    '--color-border-yellow': ['#fde047', '#ca8a04'],
    '--color-icon-yellow': ['#a16207', '#facc15'],
    '--color-text-yellow': ['#854d0e', '#fef08a'],

    // Data visualization preserves ordering and series separation using only
    // luminance. Dark-mode stops reverse so every series clears the canvas.
    '--color-data-categorical-blue': ['#0a0a0a', '#f5f5f5'],
    '--color-data-categorical-orange': ['#1c1c1c', '#e0e0e0'],
    '--color-data-categorical-purple': ['#2e2e2e', '#cccccc'],
    '--color-data-categorical-green': ['#404040', '#b8b8b8'],
    '--color-data-categorical-pink': ['#525252', '#a3a3a3'],
    '--color-data-categorical-cyan': ['#646464', '#949494'],
    '--color-data-categorical-red': ['#737373', '#858585'],
    '--color-data-categorical-teal': ['#595959', '#adadad'],
    '--color-data-categorical-brown': ['#353535', '#c2c2c2'],
    '--color-data-categorical-indigo': ['#171717', '#ebebeb'],
    '--color-data-neutral': ['#737373', '#8a8a8a'],

    '--color-data-blue-5': ['#242424', '#d4d4d4'],
    '--color-data-blue-4': ['#4a4a4a', '#b8b8b8'],
    '--color-data-blue-3': ['#707070', '#999999'],
    '--color-data-blue-2': ['#969696', '#7a7a7a'],
    '--color-data-blue-1': ['#bcbcbc', '#5c5c5c'],
    '--color-data-shamrock-5': ['#242424', '#d4d4d4'],
    '--color-data-shamrock-4': ['#4a4a4a', '#b8b8b8'],
    '--color-data-shamrock-3': ['#707070', '#999999'],
    '--color-data-shamrock-2': ['#969696', '#7a7a7a'],
    '--color-data-shamrock-1': ['#bcbcbc', '#5c5c5c'],
    '--color-data-orange-5': ['#242424', '#d4d4d4'],
    '--color-data-orange-4': ['#4a4a4a', '#b8b8b8'],
    '--color-data-orange-3': ['#707070', '#999999'],
    '--color-data-orange-2': ['#969696', '#7a7a7a'],
    '--color-data-orange-1': ['#bcbcbc', '#5c5c5c'],
    '--color-data-pink-5': ['#242424', '#d4d4d4'],
    '--color-data-pink-4': ['#4a4a4a', '#b8b8b8'],
    '--color-data-pink-3': ['#707070', '#999999'],
    '--color-data-pink-2': ['#969696', '#7a7a7a'],
    '--color-data-pink-1': ['#bcbcbc', '#5c5c5c'],
    '--color-data-purple-5': ['#242424', '#d4d4d4'],
    '--color-data-purple-4': ['#4a4a4a', '#b8b8b8'],
    '--color-data-purple-3': ['#707070', '#999999'],
    '--color-data-purple-2': ['#969696', '#7a7a7a'],
    '--color-data-purple-1': ['#bcbcbc', '#5c5c5c'],
    '--color-data-red-5': ['#242424', '#d4d4d4'],
    '--color-data-red-4': ['#4a4a4a', '#b8b8b8'],
    '--color-data-red-3': ['#707070', '#999999'],
    '--color-data-red-2': ['#969696', '#7a7a7a'],
    '--color-data-red-1': ['#bcbcbc', '#5c5c5c'],
    '--color-data-teal-5': ['#242424', '#d4d4d4'],
    '--color-data-teal-4': ['#4a4a4a', '#b8b8b8'],
    '--color-data-teal-3': ['#707070', '#999999'],
    '--color-data-teal-2': ['#969696', '#7a7a7a'],
    '--color-data-teal-1': ['#bcbcbc', '#5c5c5c'],
    '--color-data-yellow-5': ['#242424', '#d4d4d4'],
    '--color-data-yellow-4': ['#4a4a4a', '#b8b8b8'],
    '--color-data-yellow-3': ['#707070', '#999999'],
    '--color-data-yellow-2': ['#969696', '#7a7a7a'],
    '--color-data-yellow-1': ['#bcbcbc', '#5c5c5c'],
    '--color-data-gray-5': ['#242424', '#d4d4d4'],
    '--color-data-gray-4': ['#4a4a4a', '#b8b8b8'],
    '--color-data-gray-3': ['#707070', '#999999'],
    '--color-data-gray-2': ['#969696', '#7a7a7a'],
    '--color-data-gray-1': ['#bcbcbc', '#5c5c5c'],

    '--shadow-low':
      '0 1px 2px light-dark(#00000014, #00000080), 0 4px 12px light-dark(#0000000a, #00000066)',
    '--shadow-med':
      '0 2px 6px light-dark(#0000001a, #00000099), 0 12px 28px light-dark(#00000014, #00000080)',
    '--shadow-high':
      '0 4px 12px light-dark(#00000024, #000000b3), 0 24px 52px light-dark(#0000001f, #00000099)',
    '--shadow-inset-hover':
      'inset 0 0 0 2px light-dark(#0000001f, #ffffff24)',
    '--shadow-inset-selected':
      'inset 0 0 0 2px light-dark(#00000052, #ffffff52)',
    '--shadow-inset-success':
      'inset 0 0 0 2px light-dark(#0000003d, #ffffff3d)',
    '--shadow-inset-warning':
      'inset 0 0 0 2px light-dark(#00000033, #ffffff33)',
    '--shadow-inset-error':
      'inset 0 0 0 2px light-dark(#00000066, #ffffff66)',
  },

  // Keep nested media surfaces on the same warm monochrome accent palette.
  onDark: {
    tokens: {
      '--color-accent': '#ece8e1',
      '--color-accent-muted': '#292825',
      '--color-on-accent': '#111111',
      '--color-text-accent': '#ece8e1',
      '--color-icon-accent': '#ece8e1',
    },
  },
  onLight: {
    tokens: {
      '--color-accent': '#181818',
      '--color-accent-muted': '#e8e5df',
      '--color-on-accent': '#faf8f3',
      '--color-text-accent': '#181818',
      '--color-icon-accent': '#181818',
    },
  },

  components: {
    button: {
      base: {
        borderRadius: 'var(--radius-inner)',
        fontWeight: 'var(--font-weight-semibold)',
      },
      'variant:destructive': {
        backgroundColor: 'var(--color-error)',
        color: 'var(--color-on-error)',
      },
    },
    'side-nav-item': {
      base: {borderRadius: 'var(--radius-inner)'},
      selected: {
        backgroundColor: 'var(--color-background-muted)',
        color: 'var(--color-text-primary)',
      },
    },
    tab: {
      base: {borderRadius: 'var(--radius-inner)'},
      selected: {color: 'var(--color-text-primary)'},
    },
    'tab-indicator': {
      base: {backgroundColor: 'var(--color-accent)'},
    },
    banner: {
      'status:info': {
        '--color-accent-muted': 'var(--color-neutral)',
        '--color-text-primary': 'inherit',
        '--color-text-secondary': 'inherit',
        '--color-accent': 'inherit',
      },
    },
    progressbar: {
      base: {'--color-background-muted': 'var(--color-neutral)'},
      'variant:accent': {'--color-accent': 'inherit'},
      'variant:success': {'--color-success': 'inherit'},
      'variant:warning': {'--color-warning': 'inherit'},
      'variant:error': {'--color-error': 'inherit'},
    },
    badge: {
      'variant:info': {
        backgroundColor: 'var(--color-accent)',
        color: 'var(--color-on-accent)',
      },
      'variant:neutral': {
        backgroundColor: 'var(--color-background-gray)',
        color: 'var(--color-text-gray)',
      },
      'variant:success': {
        backgroundColor: 'var(--color-success)',
        color: 'var(--color-on-success)',
      },
      'variant:warning': {
        backgroundColor: 'var(--color-warning)',
        color: 'var(--color-on-warning)',
      },
      'variant:error': {
        backgroundColor: 'var(--color-error)',
        color: 'var(--color-on-error)',
      },
    },
    statusdot: {
      'variant:success': {backgroundColor: 'var(--color-success)'},
      'variant:warning': {backgroundColor: 'var(--color-warning)'},
      'variant:error': {backgroundColor: 'var(--color-error)'},
      'variant:accent': {backgroundColor: 'var(--color-accent)'},
    },
    // Keep the standard 20/24px control sizes for RadioList and menus. A
    // checked control becomes a solid monochrome dot; passcode screens can
    // safely enlarge only their four instances without changing app radios.
    'radio-indicator': {
      checked: {
        backgroundColor: 'var(--color-accent)',
        borderColor: 'var(--color-accent)',
      },
    },
    'radio-indicator-dot': {
      base: {backgroundColor: 'var(--color-accent)'},
    },
  },
});
