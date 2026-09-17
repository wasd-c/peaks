import {app, BrowserWindow, clipboard, desktopCapturer, ipcMain, nativeImage, nativeTheme, shell, type IpcMainInvokeEvent} from 'electron'
import {spawn, type ChildProcessWithoutNullStreams} from 'node:child_process'
import {existsSync, writeFileSync} from 'node:fs'
import path from 'node:path'
import readline from 'node:readline'
import {pathToFileURL} from 'node:url'
import {
  developmentRendererUrl,
  developmentServerUrl,
  decodePastedQrImagePayload,
  decodeMatchImagePayload,
  isAllowedRendererUrl,
  isBackendCommand,
  isRiotClientWindowTitle,
} from './security'
import {rejectPendingBackendRequests, resolveBackendLaunch} from './runtime'
import {createSensitiveClipboard} from './sensitiveClipboard'
import {DiscordPresence} from './discordPresence'
import {DiscordActivityHeartbeat} from './discordActivityHeartbeat'
import {Telemetry} from './telemetry'
import {CancellationToken, NsisUpdater} from 'electron-updater'
import {PEAKS_RELEASE_PROVIDER, PeaksUpdater} from './appUpdater'

let window: BrowserWindow | null = null
let backend: ChildProcessWithoutNullStreams | null = null
let serial = 0
let discordPresence: DiscordPresence | null = null
let discordHeartbeat: DiscordActivityHeartbeat | null = null
let telemetry: Telemetry | null = null
let appUpdater: PeaksUpdater | null = null
let activityRequest: {epoch: number | undefined; promise: Promise<unknown>} | null = null
const totpClipboard = createSensitiveClipboard(clipboard)
const pending = new Map<number, {resolve: (value: unknown) => void, reject: (error: Error) => void, presenceEpoch: number | undefined}>()

function startBackend() {
  const launch = resolveBackendLaunch({
    appPath: app.getAppPath(),
    environment: process.env,
    isPackaged: app.isPackaged,
    platform: process.platform,
    resourcesPath: process.resourcesPath,
    virtualenvExists: existsSync,
  })
  if (app.isPackaged && !existsSync(launch.command)) {
    throw new Error('The packaged Peaks service is missing')
  }
  const child = spawn(launch.command, launch.args, {
    env: launch.environment,
    stdio: ['pipe', 'pipe', 'pipe'], windowsHide: true,
  })
  backend = child
  child.once('spawn', () => telemetry?.track('backend.started'))
  readline.createInterface({input: child.stdout}).on('line', line => {
    try {
      const response = JSON.parse(line)
      const request = pending.get(response.id)
      if (!request) return
      pending.delete(response.id)
      if (response.error) request.reject(new Error(response.error))
      else {
        // Resolve callers normally, but a reply dispatched before a privacy
        // clear must never restore the old Discord activity.
        if (request.presenceEpoch !== undefined) discordPresence?.observe(response.result, request.presenceEpoch)
        request.resolve(response.result)
      }
    } catch { /* malformed backend output is ignored */ }
  })
  child.stderr.on('data', data => console.error(`[backend] ${data}`))
  child.on('error', error => {
    telemetry?.track('backend.failed')
    discordPresence?.clear()
    console.error(`[backend] launch failed: ${error.name}`)
    if (backend === child) backend = null
    rejectPendingBackendRequests(pending, new Error('Peaks service could not start'))
  })
  child.on('exit', () => {
    telemetry?.track('backend.stopped')
    discordPresence?.clear()
    if (backend === child) backend = null
    rejectPendingBackendRequests(pending, new Error('Peaks service stopped'))
  })
}

function callBackend(command: string, payload: unknown, presenceEpoch: number | undefined) {
  if (command === 'activity') {
    discordHeartbeat?.noteActivityRequest()
    // A background heartbeat and a waking renderer can request the same poll.
    // Never share a pre-lock request with a caller from a new privacy epoch.
    if (activityRequest && activityRequest.epoch === presenceEpoch) return activityRequest.promise
  }
  if (!backend) startBackend()
  const startedAt = Date.now()
  const telemetryEpoch = telemetry?.captureConsentEpoch() ?? null
  const promise = new Promise((resolve, reject) => {
    const id = ++serial
    pending.set(id, {resolve, reject, presenceEpoch})
    backend!.stdin.write(`${JSON.stringify({id, command, payload})}\n`)
  })
  void promise.then(
    () => telemetry?.track('command.completed', {command, outcome: 'success', duration_ms: Date.now() - startedAt}, telemetryEpoch),
    () => telemetry?.track('command.completed', {command, outcome: 'failure', duration_ms: Date.now() - startedAt}, telemetryEpoch),
  )
  if (command === 'activity') {
    const request = {epoch: presenceEpoch, promise}
    activityRequest = request
    const finished = () => { if (activityRequest === request) activityRequest = null }
    void promise.then(finished, finished)
  }
  return promise
}

interface QrWindowCapture {
  encoding: 'bgra-base64'
  height: number
  pixels: string
  width: number
}

type QrCaptureState = 'ready' | 'window_not_found' | 'window_capture_failed' | 'capture_error'

interface QrCaptureResult {
  captures: QrWindowCapture[]
  state: QrCaptureState
}

function capturePastedQrImage(value: unknown): QrWindowCapture {
  const encodedImage = decodePastedQrImagePayload(value)
  try {
    const decodedImage = nativeImage.createFromBuffer(encodedImage, {scaleFactor: 1})
    if (decodedImage.isEmpty()) {
      throw new Error('The selected file is not a readable QR image')
    }
    const {width, height} = decodedImage.getSize()
    if (
      width <= 0
      || height <= 0
      || width > 4096
      || height > 4096
      || width * height > 16_000_000
    ) {
      throw new Error('The QR image dimensions are too large')
    }
    const pixels = decodedImage.toBitmap()
    if (pixels.length !== width * height * 4) {
      pixels.fill(0)
      throw new Error('The selected file is not a readable QR image')
    }
    const capture = {
      encoding: 'bgra-base64' as const,
      height,
      pixels: pixels.toString('base64'),
      width,
    }
    pixels.fill(0)
    return capture
  } finally {
    encodedImage.fill(0)
  }
}

async function captureRiotClientWindows(): Promise<QrCaptureResult> {
  const sources = await desktopCapturer.getSources({
    types: ['window'],
    fetchWindowIcons: false,
    thumbnailSize: {width: 1920, height: 1200},
  })
  const riotSources = sources.filter(source => isRiotClientWindowTitle(source.name)).slice(0, 3)
  console.info(`[riot-qr] capture.discovery sources=${sources.length} matches=${riotSources.length}`)
  if (riotSources.length === 0) {
    return {captures: [], state: 'window_not_found'}
  }

  const captures = riotSources.flatMap<QrWindowCapture>(source => {
    if (source.thumbnail.isEmpty()) return []
    const {width, height} = source.thumbnail.getSize()
    const pixels = source.thumbnail.toBitmap()
    if (width <= 0 || height <= 0 || pixels.length !== width * height * 4) return []
    return [{
      encoding: 'bgra-base64',
      height,
      pixels: pixels.toString('base64'),
      width,
    }]
  })
  console.info(`[riot-qr] capture.complete usable=${captures.length}`)
  if (captures.length === 0) {
    return {captures: [], state: 'window_capture_failed'}
  }
  return {captures, state: 'ready'}
}

function packagedRendererUrl() {
  return pathToFileURL(path.join(app.getAppPath(), 'dist', 'index.html')).href
}

function trustedRendererUrl(candidate: string) {
  return isAllowedRendererUrl(
    candidate,
    developmentServerUrl(app.isPackaged, process.env.VITE_DEV_SERVER_URL),
    packagedRendererUrl(),
  )
}

function isTrustedSender(event: IpcMainInvokeEvent) {
  return Boolean(
    window
    && event.sender === window.webContents
    && event.senderFrame === window.webContents.mainFrame
    && trustedRendererUrl(event.senderFrame.url),
  )
}

function createWindow() {
  nativeTheme.themeSource = 'dark'
  const icon = app.isPackaged
    ? path.join(process.resourcesPath, 'brand', 'peaks-mark.png')
    : path.join(app.getAppPath(), 'src', 'renderer', 'assets', 'peaks-mark.png')
  window = new BrowserWindow({width: 1440, height: 900, minWidth: 1080, minHeight: 680, icon, backgroundColor: '#090909', titleBarStyle: 'hiddenInset', show: false, webPreferences: {preload: path.join(__dirname, 'preload.js'), contextIsolation: true, nodeIntegration: false, sandbox: true}})
  window.once('ready-to-show', () => window?.show())
  window.once('closed', () => { discordPresence?.clear(); window = null })
  window.webContents.on('render-process-gone', () => { discordPresence?.clear(); telemetry?.track('renderer.failed') })
  window.webContents.session.setPermissionCheckHandler(() => false)
  window.webContents.session.setPermissionRequestHandler((_webContents, _permission, callback) => callback(false))
  window.webContents.on('will-attach-webview', event => event.preventDefault())
  window.webContents.setWindowOpenHandler(({url}) => { if (/^https:\/\//.test(url)) shell.openExternal(url); return {action: 'deny'} })
  window.webContents.on('will-navigate', (event, url) => {
    if (!trustedRendererUrl(url)) event.preventDefault()
  })
  window.webContents.on('will-redirect', (event, url) => {
    if (!trustedRendererUrl(url)) event.preventDefault()
  })
  const devUrl = developmentRendererUrl(
    developmentServerUrl(app.isPackaged, process.env.VITE_DEV_SERVER_URL),
    process.env.PEAKS_ONBOARD_PREVIEW === '1',
  )
  void (devUrl ? window.loadURL(devUrl) : window.loadFile(path.join(app.getAppPath(), 'dist', 'index.html')))
  if (process.env.PEAKS_SCREENSHOT) window.webContents.once('did-finish-load', () => setTimeout(async () => {
    const shot = await window!.webContents.capturePage()
    writeFileSync(process.env.PEAKS_SCREENSHOT!, shot.toPNG())
    app.quit()
  }, 1200))
}

app.whenReady().then(() => {
  telemetry = new Telemetry({filename: path.join(app.getPath('userData'), 'telemetry.json'), version: app.getVersion(), platform: process.platform, available: app.isPackaged && process.env.PEAKS_DEMO !== '1'})
  appUpdater = new PeaksUpdater(app.isPackaged && process.platform === 'win32' ? new NsisUpdater(PEAKS_RELEASE_PROVIDER) : null, app.getVersion(), () => new CancellationToken(), phase => telemetry?.track('update.state', {state: phase === 'ready' ? 'downloaded' : phase}))
  appUpdater.start()
  discordPresence = new DiscordPresence(path.join(app.getPath('userData'), 'discord-presence.json'), process.env.PEAKS_DEMO === '1', process.env.PEAKS_DISCORD_APPLICATION_ID)
  // Keep Chromium's background animation throttling. Only the existing native
  // activity command needs a heartbeat when renderer timers fall behind.
  discordHeartbeat = new DiscordActivityHeartbeat({
    canRefresh: () => Boolean(window && !window.isDestroyed() && backend && discordPresence?.canRefreshActivity()),
    isBusy: () => pending.size > 0,
    refresh: () => callBackend('activity', {}, discordPresence?.captureSnapshotEpoch()),
  })
  startBackend(); ipcMain.handle('peaks:invoke', async (event, command: unknown, payload: unknown) => {
  if (!isTrustedSender(event)) {
    throw new Error('Peaks rejected an untrusted renderer request')
  }
  if (command === 'discord_presence') return discordPresence!.handle(payload ?? {})
  if (command === 'telemetry_settings') return telemetry!.handle(payload ?? {})
  if (command === 'update_status' || command === 'update_check' || command === 'update_install') return appUpdater!.handle(command, payload)
  if (command === 'copy_match_image') {
    const imageBytes = decodeMatchImagePayload(payload)
    const image = nativeImage.createFromBuffer(imageBytes)
    const {width, height} = image.getSize()
    if (image.isEmpty() || width <= 0 || height <= 0 || width > 2400 || height > 2400) {
      throw new Error('The match image could not be copied')
    }
    clipboard.writeImage(image)
    return {copied: true}
  }
  if (!isBackendCommand(command)) {
    throw new Error('Peaks rejected an unsupported request')
  }
  if (command === 'lock' || command === 'reset_application'
    || (command === 'settings' && payload && typeof payload === 'object' && 'streamerMode' in payload && payload.streamerMode === true)) {
    discordPresence?.clear()
  }
  // Capture after this command's own privacy clear, before any async native
  // capture: closing or locking the window during it also invalidates the reply.
  const presenceEpoch = discordPresence?.captureSnapshotEpoch()
  let backendPayload = payload
  if (command === 'connect_riot_client') {
    const safePayload = payload && typeof payload === 'object' && !Array.isArray(payload)
      ? {...payload as Record<string, unknown>}
      : {}
    // Renderer input can never choose the pixels. The trusted main process
    // overwrites this private field with fresh native Riot window captures.
    let capture: QrCaptureResult
    try {
      capture = await captureRiotClientWindows()
    } catch (error) {
      console.error(`[riot-qr] capture.error type=${error instanceof Error ? error.name : 'UnknownError'}`)
      capture = {captures: [], state: 'capture_error'}
    }
    safePayload.qrCaptures = capture.captures
    safePayload.qrCaptureState = capture.state
    backendPayload = safePayload
  } else if (command === 'connect_riot_qr_image') {
    const safePayload = payload && typeof payload === 'object' && !Array.isArray(payload)
      ? payload as Record<string, unknown>
      : {}
    const capture = capturePastedQrImage(safePayload.qrImage)
    backendPayload = {
      accountId: typeof safePayload.accountId === 'string' ? safePayload.accountId : '',
      qrCaptures: [capture],
      qrCaptureState: 'ready',
    }
  }
  const result = await callBackend(command, backendPayload, presenceEpoch) as {code?: string, clearAfter?: number, state?: unknown}
  if (command === 'copy_totp' && result.code) {
    totpClipboard.copy(result.code, (result.clearAfter || 15) * 1000)
    return result.state
  }
  return result
}); createWindow(); app.on('activate', () => BrowserWindow.getAllWindows().length === 0 && createWindow()) })
app.on('window-all-closed', () => { if (process.platform !== 'darwin') app.quit() })
app.on('before-quit', () => {
  telemetry?.dispose()
  appUpdater?.dispose()
  discordHeartbeat?.dispose()
  discordPresence?.dispose()
  totpClipboard.dispose()
  backend?.kill()
})
