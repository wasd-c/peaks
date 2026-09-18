import {existsSync, mkdirSync, readFileSync, renameSync, statSync, writeFileSync} from 'node:fs'
import path from 'node:path'
import {buildDiscordActivity, type DiscordActivity} from './discordActivity'
import {DiscordIpcClient, type DiscordConnectionStatus} from './discordIpc'

export interface DiscordPresenceConfig {enabled: boolean; applicationId: string}
export const PEAKS_DISCORD_APPLICATION_ID = '1549634813756178503'
export interface DiscordPresenceStatus extends DiscordPresenceConfig {
  status: DiscordConnectionStatus | 'disabled' | 'setup-required' | 'preview'
  detail: string
}
const record = (value: unknown): Record<string, unknown> | undefined => value !== null && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : undefined
const validId = (value: string) => value === '' || /^[0-9]{17,20}$/.test(value)

export function updateDiscordConfig(current: DiscordPresenceConfig, payload: unknown): DiscordPresenceConfig {
  const update = record(payload)
  if (!update || Object.keys(update).some(key => !['enabled', 'applicationId'].includes(key))) throw new Error('Invalid Discord preferences')
  if ('enabled' in update && typeof update.enabled !== 'boolean') throw new Error('Invalid Discord preference')
  if ('applicationId' in update && (typeof update.applicationId !== 'string' || !validId(update.applicationId.trim()))) {
    throw new Error('Use the public Discord Application ID: 17–20 digits, not a token or secret.')
  }
  return {
    enabled: typeof update.enabled === 'boolean' ? update.enabled : current.enabled,
    applicationId: typeof update.applicationId === 'string' ? update.applicationId.trim() : current.applicationId,
  }
}

export function readDiscordConfig(filename: string, defaultApplicationId = PEAKS_DISCORD_APPLICATION_ID): DiscordPresenceConfig {
  const fallback = {enabled: true, applicationId: validId(defaultApplicationId) ? defaultApplicationId : ''}
  try {
    if (!existsSync(filename)) return fallback
    if (statSync(filename).size > 4096) return {enabled: false, applicationId: ''}
    return updateDiscordConfig(fallback, JSON.parse(readFileSync(filename, 'utf8')))
  } catch { return {enabled: false, applicationId: ''} }
}

export interface DiscordTransport {
  setActivity(activity: DiscordActivity | null): void
  dispose(): void
}
type TransportFactory = (id: string, status: (status: DiscordConnectionStatus, detail: string) => void) => DiscordTransport

/** Consumes trusted backend snapshots; the renderer cannot submit an activity. */
export class DiscordPresence {
  private config: DiscordPresenceConfig
  private status: DiscordPresenceStatus['status'] = 'disabled'
  private detail = 'Discord Rich Presence is off.'
  private client: DiscordTransport | null = null
  private activity: DiscordActivity | null = null
  private activityClock: {game: unknown; phase: unknown; matchId: string | null; start: number} | null = null
  private unlocked = false
  private shareAllowed = false
  private lastSnapshotAt = 0
  private snapshotEpoch = 0
  private watchdog: ReturnType<typeof setInterval>

  constructor(
    private filename: string,
    private preview = false,
    defaultApplicationId = PEAKS_DISCORD_APPLICATION_ID,
    private createTransport: TransportFactory = (id, status) => new DiscordIpcClient(id, status),
  ) {
    this.config = readDiscordConfig(filename, defaultApplicationId)
    this.configure()
    this.watchdog = setInterval(() => {
      if (this.lastSnapshotAt && Date.now() - this.lastSnapshotAt > 60_000) this.expireActivity()
    }, 5000)
    this.watchdog.unref()
  }

  /** Capture when a backend request starts, before its asynchronous reply. */
  captureSnapshotEpoch() {
    return this.snapshotEpoch
  }

  canRefreshActivity() {
    return !this.preview && this.unlocked && this.shareAllowed && this.config.enabled && this.config.applicationId !== ''
  }

  observe(value: unknown, requestEpoch = this.snapshotEpoch) {
    if (requestEpoch !== this.snapshotEpoch) return
    const response = record(value)
    const snapshot = response && (typeof response.locked === 'boolean' ? response : record(response.state))
    // Even a minimal lock response is authoritative; private state and
    // settings may intentionally be absent once the vault is locked.
    if (snapshot?.locked === true) { this.clear(); return }
    if (!snapshot || typeof snapshot.locked !== 'boolean' || !record(snapshot.settings)) return
    this.unlocked = snapshot.locked === false
    const streamerMode = record(snapshot.settings)!.streamerMode
    this.shareAllowed = streamerMode === undefined || streamerMode === false
    this.lastSnapshotAt = Date.now()
    const activity = this.preview ? null : buildDiscordActivity(snapshot)
    const match = record(snapshot.currentMatch)
    this.activity = activity && match ? this.withSessionClock(activity, match) : null
    if (!this.activity && (!this.shareAllowed || snapshot.gameDetected !== true || match?.isStale !== true)) {
      this.activityClock = null
    }
    this.client?.setActivity(this.activity)
  }

  private withSessionClock(activity: DiscordActivity, match: Record<string, unknown>): DiscordActivity {
    // Match identity stays in memory; Discord receives only a fixed Unix start
    // time in seconds. Mutable stats, artwork and party size are not identity.
    const matchId = typeof match.id === 'string' && match.id.length > 0 && match.id.length <= 256 ? match.id : null
    const previous = this.activityClock
    if (!previous || previous.game !== match.game || previous.phase !== match.phase
      || previous.matchId !== null && matchId !== null && previous.matchId !== matchId) {
      const elapsed = match.phase === 'live' && typeof match.elapsed === 'string'
        ? /^(0|[1-9][0-9]{0,2}):([0-5][0-9])$/.exec(match.elapsed) : null
      const seconds = elapsed ? Number(elapsed[1]) * 60 + Number(elapsed[2]) : 0
      this.activityClock = {game: match.game, phase: match.phase, matchId, start: Math.max(0, Math.floor(Date.now() / 1000) - seconds)}
    } else if (matchId !== null) {
      // An ID can arrive after the first live snapshot or briefly disappear.
      previous.matchId = matchId
    }
    return {...activity, timestamps: {start: this.activityClock!.start}}
  }

  clear() {
    this.unlocked = false
    this.shareAllowed = false
    this.activityClock = null
    this.expireActivity()
  }

  private expireActivity() {
    // A stale publication is not an authoritative lock. Invalidate its
    // replies, but let the heartbeat request fresh state after the bridge
    // becomes idle. Explicit privacy clears revoke that eligibility above.
    this.snapshotEpoch++
    this.lastSnapshotAt = 0
    this.activity = null
    this.client?.setActivity(null)
  }

  handle(payload: unknown = {}) {
    const update = record(payload)
    if (!update) throw new Error('Invalid Discord preferences')
    if (Object.keys(update).length) {
      if (!this.unlocked) throw new Error('Unlock Peaks to change Discord preferences')
      const next = updateDiscordConfig(this.config, update)
      if (next.enabled === this.config.enabled && next.applicationId === this.config.applicationId) return this.getStatus()
      // Only this public ID and the opt-out preference are stored here.
      mkdirSync(path.dirname(this.filename), {recursive: true})
      const temporary = `${this.filename}.tmp`
      writeFileSync(temporary, `${JSON.stringify(next, null, 2)}\n`, {mode: 0o600})
      renameSync(temporary, this.filename)
      this.config = next
      this.configure()
    }
    return this.getStatus()
  }

  getStatus(): DiscordPresenceStatus {
    return {...this.config, status: this.status, detail: this.detail}
  }

  private configure() {
    this.client?.dispose()
    this.client = null
    if (this.preview) { this.status = 'preview'; this.detail = 'Preview only. Demo matches are never shared to Discord.'; return }
    if (!this.config.enabled) { this.status = 'disabled'; this.detail = 'Discord Rich Presence is off.'; return }
    if (!this.config.applicationId) { this.status = 'setup-required'; this.detail = 'Add the public Application ID for Peaks to connect Discord.'; return }
    this.status = 'connecting'
    this.detail = 'Connecting to Discord desktop…'
    this.client = this.createTransport(this.config.applicationId, (status, detail) => { this.status = status; this.detail = detail })
    this.client.setActivity(this.activity)
  }

  dispose() {
    clearInterval(this.watchdog)
    this.client?.dispose()
    this.client = null
  }
}
