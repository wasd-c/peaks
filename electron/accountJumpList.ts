/** Windows taskbar shortcuts for the most recently used accounts. */

export const connectAccountSwitch = '--peaks-connect-account'
export const RECENT_ACCOUNT_LIMIT = 3

/** Only the backend's per-session renderer handles may travel on a command line. */
const ACCOUNT_HANDLE = /^account-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/

export interface RecentAccountShortcut {
  accountId: string
  title: string
}

function record(value: unknown): Record<string, unknown> | null {
  return value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : null
}

/**
 * Returns the shortcut list a backend reply implies, or `undefined` when the
 * reply is not an application state (activity polls, search results…).
 * A locked vault or streamer mode yields no shortcuts, so Riot IDs never sit in
 * the taskbar while Peaks hides them.
 */
export function recentAccountShortcuts(value: unknown, limit = RECENT_ACCOUNT_LIMIT): RecentAccountShortcut[] | undefined {
  const state = record(value)
  if (!state || !Array.isArray(state.accounts) || typeof state.locked !== 'boolean') return undefined
  if (state.locked || record(state.settings)?.streamerMode === true) return []
  return state.accounts
    .map(record)
    .filter((account): account is Record<string, unknown> => Boolean(
      account
      && account.canConnectQr === true
      && typeof account.id === 'string' && ACCOUNT_HANDLE.test(account.id)
      && typeof account.riotId === 'string' && account.riotId.trim(),
    ))
    .map(account => ({
      account,
      lastConnectedAt: typeof account.lastConnectedAt === 'number' && Number.isFinite(account.lastConnectedAt) ? account.lastConnectedAt : 0,
    }))
    .sort((left, right) => right.lastConnectedAt - left.lastConnectedAt)
    .slice(0, limit)
    .map(({account}) => {
      const riotId = String(account.riotId).trim()
      const nickname = typeof account.nickname === 'string' ? account.nickname.trim() : ''
      return {accountId: String(account.id), title: (nickname || riotId).slice(0, 64)}
    })
}

export function shortcutsSignature(shortcuts: RecentAccountShortcut[]) {
  return JSON.stringify(shortcuts.map(({accountId, title}) => [accountId, title]))
}

/** The account a taskbar shortcut asked to connect, if the command line carries a valid one. */
export function requestedAccountConnection(commandLine: readonly string[]): string | null {
  const prefix = `${connectAccountSwitch}=`
  const argument = commandLine.find(value => value.startsWith(prefix))
  const accountId = argument?.slice(prefix.length) ?? ''
  return ACCOUNT_HANDLE.test(accountId) ? accountId : null
}
