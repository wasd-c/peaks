import type {CancellationToken, UpdateInfo} from 'electron-updater'
import type {UpdatePhase, UpdateState} from './updaterTypes'

export const PEAKS_RELEASE_PROVIDER = Object.freeze({
  provider: 'github' as const, owner: 'wasd-c', repo: 'peaks', private: false, protocol: 'https' as const,
})
const INITIAL_CHECK_DELAY = 10_000
const CHECK_INTERVAL = 6 * 60 * 60 * 1000
const MAX_DOWNLOAD_TIME = 30 * 60 * 1000

export interface UpdaterDriver {
  autoDownload: boolean
  autoInstallOnAppQuit: boolean
  allowPrerelease: boolean
  allowDowngrade: boolean
  logger: unknown
  on(event: string, listener: (...args: never[]) => void): unknown
  removeListener(event: string, listener: (...args: never[]) => void): unknown
  checkForUpdates(): Promise<unknown>
  downloadUpdate(cancellationToken: CancellationToken): Promise<string[]>
  quitAndInstall(isSilent: boolean, isForceRunAfter: boolean): void
}

// Public release metadata must name a stable version and an in-release installer.
// electron-updater independently verifies its SHA-512 before emitting downloaded.
export function validRelease(info: UpdateInfo): boolean {
  return Boolean(info && typeof info.version === 'string' && info.version.length <= 32
    && /^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$/.exec(info.version)?.[0] === info.version
    && Array.isArray(info.files) && info.files.length > 0 && info.files.length <= 8
    && info.files.every(file => file && typeof file.url === 'string'
      && /^[a-zA-Z0-9][a-zA-Z0-9._ -]*\.(exe|blockmap)$/.test(file.url)
      && typeof file.sha512 === 'string' && /^[A-Za-z0-9+/]{86}==$/.test(file.sha512)
      && (file.size === undefined || Number.isSafeInteger(file.size) && file.size > 0 && file.size <= 2_147_483_648))
    && info.files.some(file => file.url.endsWith('.exe')))
}

/** One user action downloads, verifies, installs, and relaunches the NSIS app. */
export class PeaksUpdater {
  private state: UpdateState
  private available = false
  private installRequested = false
  private disposed = false
  private checkPending: Promise<UpdateState> | null = null
  private downloadPending = false
  private downloadToken: CancellationToken | null = null
  private initialTimer?: ReturnType<typeof setTimeout>
  private interval?: ReturnType<typeof setInterval>
  private installTimer?: ReturnType<typeof setTimeout>
  private downloadTimer?: ReturnType<typeof setTimeout>
  private readonly listeners: [string, (...args: never[]) => void][] = []

  constructor(
    private readonly driver: UpdaterDriver | null,
    currentVersion: string,
    private readonly cancellationToken: () => CancellationToken,
    private readonly onPhaseChanged?: (phase: UpdatePhase) => void,
  ) {
    this.state = {phase: driver ? 'idle' : 'unsupported', currentVersion, message: driver ? 'Check for updates' : 'Updates are available in the installed Windows app.'}
    if (!driver) return
    driver.autoDownload = false
    driver.autoInstallOnAppQuit = false
    driver.allowPrerelease = false
    driver.allowDowngrade = false
    // Library errors can include request headers and local paths. Only our
    // bounded status messages cross into the UI or diagnostic event stream.
    driver.logger = null
    this.listen('update-available', (info: UpdateInfo) => {
      if (!validRelease(info)) {
        this.available = false
        this.fail('The release files could not be verified. Try again later.', 'check')
        return
      }
      this.available = true
      this.set({phase: 'available', version: info.version, message: `Peaks ${info.version} is available. Update and restart.`})
    })
    this.listen('update-not-available', () => {
      this.available = false
      this.set({phase: 'idle', message: 'Peaks is up to date.'})
    })
    this.listen('download-progress', (progress: {percent: number}) => {
      if (!this.installRequested || !this.downloadPending || !Number.isFinite(progress.percent)) return
      this.set({phase: 'downloading', percent: Math.max(0, Math.min(100, Math.floor(progress.percent))), message: 'Downloading update. Peaks will restart when it is ready.'})
    })
    this.listen('update-downloaded', (info: UpdateInfo) => {
      if (!this.installRequested || !this.downloadPending || !validRelease(info) || info.version !== this.state.version) return
      clearTimeout(this.downloadTimer)
      this.set({phase: 'ready', percent: 100, message: 'Update verified. Restarting Peaks…'})
      this.installTimer = setTimeout(() => this.finishInstall(), 800)
    })
    this.listen('error', () => {
      this.fail(this.installRequested ? 'The update could not finish. Retry the update.' : 'Could not check for updates. Try again.', this.available ? 'install' : 'check')
    })
  }

  snapshot(): UpdateState { return {...this.state} }

  start() {
    if (!this.driver || this.disposed || this.interval) return
    this.initialTimer = setTimeout(() => { void this.check() }, INITIAL_CHECK_DELAY)
    this.interval = setInterval(() => {
      if (this.state.phase === 'idle' || this.state.phase === 'error' && !this.available) void this.check()
    }, CHECK_INTERVAL)
    this.initialTimer.unref?.()
    this.interval.unref?.()
  }

  check(): Promise<UpdateState> {
    if (!this.driver || this.disposed || this.installRequested || this.downloadPending || this.available) return Promise.resolve(this.snapshot())
    if (this.checkPending) return this.checkPending
    this.set({phase: 'checking', message: 'Checking for updates…'})
    const pending = Promise.resolve().then(() => this.driver!.checkForUpdates()).then(() => this.snapshot()).catch(() => {
      this.fail('Could not check for updates. Try again.', 'check')
      return this.snapshot()
    }).finally(() => { if (this.checkPending === pending) this.checkPending = null })
    this.checkPending = pending
    return pending
  }

  install(): UpdateState {
    if (!this.driver || this.disposed || this.installRequested || this.downloadPending) return this.snapshot()
    if (!this.available) return this.snapshot()
    this.installRequested = true
    this.downloadPending = true
    this.downloadToken = this.cancellationToken()
    this.set({phase: 'downloading', percent: 0, message: 'Downloading update. Peaks will restart when it is ready.'})
    this.downloadTimer = setTimeout(() => {
      this.downloadToken?.cancel()
      this.fail('The download timed out. Retry when your connection is ready.', 'install')
    }, MAX_DOWNLOAD_TIME)
    const token = this.downloadToken
    void Promise.resolve().then(() => this.driver!.downloadUpdate(token)).then(files => {
      if (!this.installRequested) return
      if (!files.length || this.state.phase === 'downloading') this.fail('The update could not be verified. Retry the update.', 'install')
    }).catch(() => {
      if (this.installRequested) this.fail('The update could not finish. Retry the update.', 'install')
    }).finally(() => { this.downloadPending = false })
    return this.snapshot()
  }

  handle(command: string, payload: unknown): UpdateState | Promise<UpdateState> {
    if (payload !== undefined && (!payload || typeof payload !== 'object' || Array.isArray(payload) || Object.keys(payload).length)) {
      throw new Error('Invalid update request')
    }
    if (command === 'update_status') return this.snapshot()
    if (command === 'update_check') return this.check()
    if (command === 'update_install') return this.install()
    throw new Error('Unsupported update request')
  }

  dispose() {
    this.disposed = true
    this.installRequested = false
    clearTimeout(this.initialTimer)
    clearInterval(this.interval)
    clearTimeout(this.installTimer)
    clearTimeout(this.downloadTimer)
    this.downloadToken?.cancel()
    for (const [event, listener] of this.listeners) this.driver?.removeListener(event, listener)
    this.listeners.length = 0
  }

  private listen(event: string, listener: (...args: never[]) => void) {
    const guarded = (...args: never[]) => { if (!this.disposed) listener(...args) }
    this.listeners.push([event, guarded])
    this.driver?.on(event, guarded)
  }

  private set(next: Partial<UpdateState> & Pick<UpdateState, 'phase' | 'message'>) {
    if (this.disposed) return
    const changed = this.state.phase !== next.phase
    this.state = {...this.state, percent: undefined, retry: undefined, ...next}
    if (changed) this.onPhaseChanged?.(next.phase)
  }

  private fail(message: string, retry: 'check' | 'install') {
    this.installRequested = false
    clearTimeout(this.installTimer)
    clearTimeout(this.downloadTimer)
    this.set({phase: 'error', message, retry})
  }

  private finishInstall() {
    if (!this.driver || this.disposed || !this.installRequested || this.state.phase !== 'ready') return
    this.set({phase: 'installing', percent: 100, message: 'Restarting Peaks…'})
    try { this.driver.quitAndInstall(true, true) }
    catch { this.fail('Peaks could not restart. Retry the update.', 'install') }
  }
}
