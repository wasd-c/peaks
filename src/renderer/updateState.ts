import type {UpdateState} from '../../electron/updaterTypes'

export type {UpdateState} from '../../electron/updaterTypes'

export function updateControl(state: UpdateState) {
  const busy = ['checking', 'downloading', 'ready', 'installing'].includes(state.phase)
  const install = state.phase === 'available' || state.phase === 'error' && state.retry === 'install'
  return {
    visible: state.phase !== 'unsupported',
    busy,
    install,
    label: install ? `Update to Peaks ${state.version} and restart` : state.phase === 'error' ? 'Retry update check' : 'Check for updates',
    caption: state.phase === 'available' ? 'Update'
      : state.phase === 'error' ? 'Retry'
      : state.phase === 'downloading' ? `${state.percent ?? 0}%`
      : state.phase === 'ready' || state.phase === 'installing' ? 'Restarting'
      : state.phase === 'checking' ? 'Checking' : '',
    command: install ? 'update_install' : 'update_check',
  }
}
