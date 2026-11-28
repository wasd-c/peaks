import {useSyncExternalStore, type ReactNode} from 'react'
import {App, ConfigProvider, theme as antTheme} from 'antd'
import type {ThemeConfig} from 'antd'

export type PeaksTheme = 'peaks' | 'riot' | 'valorant' | 'league' | 'tft'

/* Accent per surface, kept in step with theme/tokens.css. */
const ACCENT: Record<PeaksTheme, {primary: string; onPrimary: string; surface: string; muted: string}> = {
  peaks: {primary: '#ece8e1', onPrimary: '#111111', surface: '#101113', muted: '#1d1d1f'},
  riot: {primary: '#ece8e1', onPrimary: '#111111', surface: '#101113', muted: '#1d1d1f'},
  valorant: {primary: '#ff6776', onPrimary: '#1a0f14', surface: '#131116', muted: '#211a22'},
  league: {primary: '#d4bb7c', onPrimary: '#101d24', surface: '#0c1820', muted: '#172b35'},
  tft: {primary: '#c4a0f3', onPrimary: '#1c1329', surface: '#161221', muted: '#271f36'},
}

export function antThemeFor(name: PeaksTheme): ThemeConfig {
  const accent = ACCENT[name]
  return {
    algorithm: antTheme.darkAlgorithm,
    token: {
      colorPrimary: accent.primary,
      colorTextLightSolid: accent.onPrimary,
      colorInfo: accent.primary,
      colorSuccess: '#8ab7a0',
      colorWarning: '#cfb887',
      colorError: '#fb7185',
      colorBgBase: '#08090b',
      colorBgLayout: '#08090b',
      colorBgContainer: '#17181b',
      colorBgElevated: '#1b1b1d',
      colorBorder: '#ece8e12b',
      colorBorderSecondary: '#ece8e117',
      colorText: '#f0f1f3',
      colorTextSecondary: '#a5a8b0',
      colorTextTertiary: '#7d8088',
      colorFillSecondary: accent.muted,
      fontFamily: '"Segoe UI Variable", "Segoe UI", -apple-system, BlinkMacSystemFont, Helvetica, Arial, sans-serif',
      fontSize: 14,
      borderRadius: 12,
      borderRadiusLG: 18,
      borderRadiusSM: 8,
      controlHeight: 34,
      motionDurationMid: '0.2s',
    },
    components: {
      Layout: {headerBg: '#08090b', siderBg: '#08090b', bodyBg: '#08090b', headerHeight: 56, headerPadding: '0 20px'},
      Card: {colorBgContainer: accent.surface},
      Table: {headerBg: 'transparent', colorBgContainer: 'transparent', rowHoverBg: '#ffffff0a', headerSplitColor: 'transparent'},
      Tabs: {itemSelectedColor: '#f0f1f3', inkBarColor: accent.primary},
      Segmented: {itemSelectedBg: '#2a2b2f', trackBg: '#141517'},
      Modal: {contentBg: '#141517', headerBg: '#141517'},
      // Primary text is dark (for accent buttons); tooltips sit on a dark surface, so their text stays light.
      Tooltip: {colorBgSpotlight: '#2a2b2f', colorTextLightSolid: '#f0f1f3'},
      Button: {primaryShadow: 'none', defaultShadow: 'none'},
      Menu: {itemBg: 'transparent', darkItemBg: 'transparent'},
    },
  }
}

const systemMotion = typeof window !== 'undefined' && window.matchMedia
  ? window.matchMedia('(prefers-reduced-motion: reduce)') : undefined

function subscribeMotion(change: () => void) {
  systemMotion?.addEventListener('change', change)
  return () => systemMotion?.removeEventListener('change', change)
}

export function MotionPreference({reduce, children}: {reduce?: boolean; children: ReactNode}) {
  // CSS-only cancellation can strand an Ant dialog at its initial opacity.
  const systemReduced = useSyncExternalStore(subscribeMotion, () => Boolean(systemMotion?.matches), () => false)
  return <ConfigProvider theme={{token: {motion: !(reduce || systemReduced)}}}>{children}</ConfigProvider>
}

/** Root provider: Ant Design's dark theme with Peaks's palette, plus toasts. */
export function PeaksProvider({children}: {children: ReactNode}) {
  return <ConfigProvider theme={antThemeFor('peaks')}>
    <App component={false} notification={{placement: 'bottomRight'}}>{children}</App>
  </ConfigProvider>
}

/** Scopes a game's accent to a profile: the tokens through CSS, the components through Ant Design. */
export function Theme({theme, children}: {theme: PeaksTheme; mode?: 'dark'; children?: ReactNode}) {
  return <ConfigProvider theme={antThemeFor(theme)}>
    <div data-peaks-theme={theme}>{children}</div>
  </ConfigProvider>
}
