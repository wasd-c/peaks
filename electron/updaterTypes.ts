export type UpdatePhase = 'unsupported' | 'idle' | 'checking' | 'available' | 'downloading' | 'ready' | 'installing' | 'error'

/** The renderer receives status only, never URLs, local paths, or release HTML. */
export interface UpdateState {
  phase: UpdatePhase
  currentVersion: string
  version?: string
  percent?: number
  message: string
  retry?: 'check' | 'install'
}
