import {mkdirSync, readFileSync, renameSync, statSync, writeFileSync} from 'node:fs'
import path from 'node:path'

export const TELEMETRY_ENDPOINT = 'https://metrics.gemstud.io/peaks/v1/events'
const EVENTS = new Set(['app.started', 'backend.started', 'backend.failed', 'backend.stopped', 'renderer.failed', 'command.completed', 'update.state'])
// Only operation names are collected, including for account/security actions.
// Their arguments, results, errors and clipboard contents never enter the event.
const COMMANDS = new Set([
  'state', 'activity', 'refresh', 'search', 'settings',
  'add_account', 'remove_account', 'set_account_icon', 'import_session', 'connect_riot_client', 'connect_riot_qr_image',
  'pin', 'lock', 'change_pin', 'reset_application', 'api_key',
  'prepare_totp_setup', 'confirm_totp_setup', 'cancel_totp_setup', 'copy_totp', 'enable_riot_mfa',
  'toggle_follow', 'toggle_watchlist', 'copy_match_image', 'discord_presence',
  'update_check', 'update_install', 'release_history', 'release_history_ack',
  // Keep schema-1 compatibility with previously accepted names.
  'player', 'match', 'matches', 'account', 'follow', 'unfollow',
])
const UPDATE_STATES = new Set(['checking', 'available', 'downloading', 'downloaded', 'installing', 'error', 'idle', 'up-to-date'])
const PLATFORMS = new Set(['win32', 'darwin', 'linux'])
const record = (value: unknown): Record<string, unknown> | undefined => value !== null && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : undefined

export interface TelemetryEvent {
  event: string
  version: string
  platform: string
  command?: string
  outcome?: 'success' | 'failure'
  duration_ms?: number
  state?: string
}

/** Build from fixed fields only. Payloads, exceptions, identities and URLs are never copied. */
export function safeTelemetryEvent(name: unknown, fields: unknown, version: string, platform: string): TelemetryEvent | null {
  if (typeof name !== 'string' || !EVENTS.has(name) || !/^\d{1,4}\.\d{1,4}\.\d{1,4}$/.test(version) || !PLATFORMS.has(platform)) return null
  const event: TelemetryEvent = {event: name, version, platform}
  const input = record(fields) ?? {}
  if (name === 'command.completed') {
    if (typeof input.command !== 'string' || !COMMANDS.has(input.command)) return null
    if (input.outcome !== 'success' && input.outcome !== 'failure') return null
    event.command = input.command
    event.outcome = input.outcome
    if (typeof input.duration_ms === 'number' && Number.isFinite(input.duration_ms) && input.duration_ms >= 0) event.duration_ms = Math.min(300_000, Math.round(input.duration_ms / 100) * 100)
  }
  if (name === 'update.state') {
    if (typeof input.state !== 'string' || !UPDATE_STATES.has(input.state)) return null
    event.state = input.state
  }
  return event
}

export interface TelemetryStatus {enabled: boolean; available: boolean}
interface TelemetryOptions {
  filename: string
  version: string
  platform: string
  available: boolean
  send?: typeof fetch
  now?: () => number
}

/** Optional, bounded technical diagnostics. No persistent device/session ID or disk event queue. */
export class Telemetry {
  private enabled = false
  private queue: TelemetryEvent[] = []
  private lastEvent = new Map<string, number>()
  private timer: ReturnType<typeof setInterval>
  private request: AbortController | null = null
  private disposed = false
  private epoch = 0

  constructor(private options: TelemetryOptions) {
    try {
      if (statSync(options.filename).size <= 1024) this.enabled = record(JSON.parse(readFileSync(options.filename, 'utf8')))?.enabled === true
    } catch { /* Optional diagnostics start off on a new or damaged preference file. */ }
    this.timer = setInterval(() => { void this.flush() }, 60_000)
    this.timer.unref()
    this.track('app.started')
  }

  getStatus(): TelemetryStatus {return {enabled: this.enabled, available: this.options.available}}

  /** Bind asynchronous work to the consent that existed when it began. */
  captureConsentEpoch(): number | null {
    return this.enabled && this.options.available && !this.disposed ? this.epoch : null
  }

  /** Cover preparation, execution and result handling without inspecting any data. */
  async runCommand<T>(command: unknown, action: () => T | Promise<T>): Promise<T> {
    const consentEpoch = this.captureConsentEpoch()
    const startedAt = (this.options.now ?? Date.now)()
    let outcome: 'success' | 'failure' = 'failure'
    try {
      const result = await action()
      outcome = 'success'
      return result
    } finally {
      this.track('command.completed', {command, outcome, duration_ms: (this.options.now ?? Date.now)() - startedAt}, consentEpoch)
    }
  }

  handle(payload: unknown = {}): TelemetryStatus {
    const input = record(payload)
    if (!input || Object.keys(input).some(key => key !== 'enabled') || ('enabled' in input && typeof input.enabled !== 'boolean')) throw new Error('Invalid diagnostic preference')
    if (typeof input.enabled === 'boolean') {
      const next = input.enabled
      mkdirSync(path.dirname(this.options.filename), {recursive: true})
      const temporary = `${this.options.filename}.tmp`
      writeFileSync(temporary, `${JSON.stringify({enabled: next})}\n`, {mode: 0o600})
      renameSync(temporary, this.options.filename)
      this.enabled = next
      this.epoch++
      this.queue = []
      this.lastEvent.clear()
      this.request?.abort()
      if (next) this.track('app.started')
    }
    return this.getStatus()
  }

  track(name: unknown, fields: unknown = {}, consentEpoch: number | null = this.captureConsentEpoch()) {
    if (!this.enabled || !this.options.available || this.disposed) return
    if (consentEpoch === null || consentEpoch !== this.epoch) return
    const event = safeTelemetryEvent(name, fields, this.options.version, this.options.platform)
    if (!event) return
    const key = `${event.event}:${event.command ?? ''}:${event.outcome ?? ''}:${event.state ?? ''}`
    const now = (this.options.now ?? Date.now)()
    // Polls and repeated failures contribute at most one record per category/minute.
    const previous = this.lastEvent.get(key)
    if (previous !== undefined && now - previous < 60_000) return
    if (this.queue.length >= 32) return
    this.lastEvent.set(key, now)
    this.queue.push(event)
  }

  async flush(): Promise<void> {
    if (!this.enabled || !this.options.available || this.disposed || this.request || !this.queue.length) return
    const controller = new AbortController()
    this.request = controller
    const batch = this.queue.splice(0, 32)
    const timeout = setTimeout(() => controller.abort(), 8000)
    timeout.unref()
    try {
      const response = await (this.options.send ?? fetch)(TELEMETRY_ENDPOINT, {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({schema: 1, events: batch}), signal: controller.signal,
        redirect: 'error', credentials: 'omit',
      })
      // No response data is needed. Failed delivery is deliberately not persisted/replayed.
      await response.body?.cancel()
    } catch { /* Diagnostics must never interrupt Peaks or create a retry storm. */ }
    finally {
      clearTimeout(timeout)
      if (this.request === controller) this.request = null
      // Consent changes clear the old queue synchronously. An older request
      // finishing after a fresh opt-in must not erase the new consent's data.
    }
  }

  dispose() {
    this.disposed = true
    clearInterval(this.timer)
    this.request?.abort()
    this.queue = []
    this.lastEvent.clear()
  }
}
