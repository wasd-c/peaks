import {app, BrowserWindow, clipboard, ipcMain, Menu, nativeImage, nativeTheme, shell, Tray, type IpcMainInvokeEvent} from 'electron'
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
  localRiotConnectPayload,
} from './security'
import {rejectPendingBackendRequests, resolveBackendLaunch} from './runtime'
import {createSensitiveClipboard} from './sensitiveClipboard'
import {DiscordPresence} from './discordPresence'
import {DiscordActivityHeartbeat} from './discordActivityHeartbeat'
import {Telemetry} from './telemetry'
import {CancellationToken, NsisUpdater} from 'electron-updater'
import {PEAKS_RELEASE_PROVIDER, PeaksUpdater} from './appUpdater'
import {ReleaseHistory} from './releaseHistory'
import {protectStdio} from './stdio'
import {readWindowBehavior, writeWindowBehavior} from './windowBehavior'

protectStdio()

let window: BrowserWindow | null = null
let tray: Tray | null = null
let quitting = false
let minimizeOnClose = true
let windowBehaviorFile = ''
const quitSwitch = '--quit-peaks'
const singleInstance = app.requestSingleInstanceLock()
let backend: ChildProcessWithoutNullStreams | null = null
let serial = 0
let discordPresence: DiscordPresence | null = null
let discordHeartbeat: DiscordActivityHeartbeat | null = null
let telemetry: Telemetry | null = null
let appUpdater: PeaksUpdater | null = null
let releaseHistory: ReleaseHistory | null = null
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
  // Python writes sanitized diagnostics to its rotating peaks.log. Do not copy
  // arbitrary library stderr/tracebacks (which can contain credentials) to Electron.
  child.stderr.resume()
  child.on('error', () => {
    telemetry?.track('backend.failed')
    discordPresence?.clear()
    console.error('[backend] launch failed')
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
  const promise = new Promise((resolve, reject) => {
    const id = ++serial
    pending.set(id, {resolve, reject, presenceEpoch})
    backend!.stdin.write(`${JSON.stringify({id, command, payload})}\n`)
  })
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
  window.on('close', event => {
    if (quitting) return
    if (minimizeOnClose) {
      event.preventDefault()
      window?.hide()
      return
    }
    quitting = true
    app.quit()
  })
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

function showWindow() {
  if (!window || window.isDestroyed()) { createWindow(); return }
  if (window.isMinimized()) window.restore()
  window.show()
  window.focus()
}

function nativeWindowLabels() {
  const locale = app.getLocale().toLowerCase()
  if (locale.startsWith('fr')) return {open: 'Ouvrir Peaks', quit: 'Quitter Peaks', quitDescription: 'Fermer complètement Peaks'}
  if (locale.startsWith('ko')) return {open: 'Peaks 열기', quit: 'Peaks 종료', quitDescription: 'Peaks 완전히 종료'}
  return {open: 'Open Peaks', quit: 'Quit Peaks', quitDescription: 'Close Peaks completely'}
}

function createTray() {
  const labels = nativeWindowLabels()
  const image = process.platform === 'win32' ? 'peaks-mark.ico' : 'peaks-mark.png'
  const icon = app.isPackaged
    ? path.join(process.resourcesPath, 'brand', image)
    : path.join(app.getAppPath(), 'src', 'renderer', 'assets', image)
  tray = new Tray(icon)
  tray.setToolTip('Peaks')
  tray.setContextMenu(Menu.buildFromTemplate([
    {label: labels.open, click: showWindow},
    {type: 'separator'},
    {label: labels.quit, click: () => { quitting = true; app.quit() }},
  ]))
  tray.on('click', showWindow)
}

app.on('second-instance', (_event, commandLine) => {
  if (commandLine.includes(quitSwitch)) { quitting = true; app.quit(); return }
  showWindow()
})

app.whenReady().then(() => {
  if (!singleInstance || process.argv.includes(quitSwitch)) { app.quit(); return }
  const userData = app.getPath('userData')
  windowBehaviorFile = path.join(userData, 'window-behavior.json')
  minimizeOnClose = readWindowBehavior(windowBehaviorFile).minimizeOnClose
  // Detect upgrades from builds that predate release-history.json before any
  // services or renderer create preferences. Inspect file existence only.
  const existingInstallation = ['discord-presence.json', 'telemetry.json', path.join('Local Storage', 'leveldb', 'CURRENT')]
    .some(filename => existsSync(path.join(userData, filename)))
  releaseHistory = new ReleaseHistory(path.join(userData, 'release-history.json'), app.getVersion(), app.isPackaged && process.env.PEAKS_DEMO !== '1', existingInstallation)
  telemetry = new Telemetry({filename: path.join(app.getPath('userData'), 'telemetry.json'), version: app.getVersion(), platform: process.platform, available: app.isPackaged && process.env.PEAKS_DEMO !== '1'})
  appUpdater = new PeaksUpdater(app.isPackaged && process.platform === 'win32' ? new NsisUpdater(PEAKS_RELEASE_PROVIDER) : null, app.getVersion(), () => new CancellationToken(), phase => telemetry?.track('update.state', {state: phase === 'ready' ? 'downloaded' : phase}))
  appUpdater.start()
  discordPresence = new DiscordPresence(path.join(app.getPath('userData'), 'discord-presence.json'), process.env.PEAKS_DEMO === '1', process.env.PEAKS_DISCORD_APPLICATION_ID)
  createTray()
  if (process.platform === 'win32' && app.isPackaged) {
    const labels = nativeWindowLabels()
    app.setAppUserModelId('local.peaks.desktop')
    app.setUserTasks([{
      program: process.execPath,
      arguments: quitSwitch,
      iconPath: process.execPath,
      iconIndex: 0,
      title: labels.quit,
      description: labels.quitDescription,
    }])
  }
  // Keep match capture running when the renderer is throttled in the tray.
  discordHeartbeat = new DiscordActivityHeartbeat({
    canRefresh: () => Boolean(window && !window.isDestroyed() && (!window.isVisible() || (backend && discordPresence?.canRefreshActivity()))),
    isBusy: () => pending.size > 0,
    refresh: () => telemetry!.runCommand('activity', () => callBackend('activity', {}, discordPresence?.captureSnapshotEpoch())),
  })
  startBackend(); ipcMain.handle('peaks:invoke', async (event, command: unknown, payload: unknown) => {
  if (!isTrustedSender(event)) {
    throw new Error('Peaks rejected an untrusted renderer request')
  }
  if (command === 'window_behavior') {
    if (payload && typeof payload === 'object' && 'minimizeOnClose' in payload) {
      minimizeOnClose = writeWindowBehavior(windowBehaviorFile, payload).minimizeOnClose
    }
    return {minimizeOnClose}
  }
  if (command === 'telemetry_settings') return telemetry!.handle(payload ?? {})
  return telemetry!.runCommand(command, async () => {
  if (command === 'discord_presence') return discordPresence!.handle(payload ?? {})
  if (command === 'update_status' || command === 'update_check' || command === 'update_install') return appUpdater!.handle(command, payload)
  if (command === 'release_history' || command === 'release_history_ack') return releaseHistory!.handle(command, payload ?? {})
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
    // The Python service obtains Riot's own local challenge after validating
    // the chosen identity. The renderer cannot supply a challenge or endpoint.
    backendPayload = localRiotConnectPayload(payload)
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
  })
}); createWindow(); app.on('activate', showWindow) })
app.on('window-all-closed', () => { if (process.platform !== 'darwin') app.quit() })
app.on('before-quit', () => {
  quitting = true
  tray?.destroy()
  tray = null
  telemetry?.dispose()
  appUpdater?.dispose()
  discordHeartbeat?.dispose()
  discordPresence?.dispose()
  totpClipboard.dispose()
  backend?.kill()
})
