import {randomUUID} from 'node:crypto'
import net, {type Socket} from 'node:net'
import os from 'node:os'
import path from 'node:path'
import type {DiscordActivity} from './discordActivity'

export type DiscordConnectionStatus = 'connecting' | 'connected' | 'waiting-for-discord' | 'error'
const MAX_FRAME_BYTES = 64 * 1024
const RETRY_MS = 15_000
const UPDATE_MS = 15_000

export function discordPipePaths(platform = process.platform, environment = process.env): string[] {
  const directory = environment.XDG_RUNTIME_DIR || environment.TMPDIR || environment.TMP || environment.TEMP || os.tmpdir()
  return Array.from({length: 10}, (_, index) => platform === 'win32'
    ? `\\\\?\\pipe\\discord-ipc-${index}`
    : path.join(directory, `discord-ipc-${index}`))
}

export function encodeDiscordFrame(opcode: number, payload: unknown): Buffer {
  const body = Buffer.from(JSON.stringify(payload), 'utf8')
  if (body.length > MAX_FRAME_BYTES) throw new Error('Discord activity is too large')
  const header = Buffer.alloc(8)
  header.writeUInt32LE(opcode, 0)
  header.writeUInt32LE(body.length, 4)
  return Buffer.concat([header, body])
}

/** Local IPC only: no Discord account token, OAuth scope, or chat access. */
export class DiscordIpcClient {
  private socket: Socket | null = null
  private ready = false
  private closed = false
  private connecting = false
  private generation = 0
  private buffer: Buffer = Buffer.alloc(0)
  private desired: DiscordActivity | null = null
  private sent: string | undefined
  private pendingNonce: string | null = null
  private sentAt = 0
  private nextAttempt = 0
  private handshakeTimer: ReturnType<typeof setTimeout> | undefined
  private timer: ReturnType<typeof setInterval>

  constructor(
    private applicationId: string,
    private onStatus: (status: DiscordConnectionStatus, detail: string) => void,
    private paths = discordPipePaths(),
  ) {
    if (!/^[0-9]{17,20}$/.test(applicationId)) throw new Error('Enter a valid Discord Application ID')
    this.timer = setInterval(() => this.tick(), 1000)
    this.timer.unref()
    this.tick()
  }

  setActivity(activity: DiscordActivity | null) {
    this.desired = activity
    this.flush()
  }

  private tick() {
    if (this.closed) return
    if (!this.socket && !this.connecting && Date.now() >= this.nextAttempt) {
      this.connecting = true
      this.onStatus('connecting', 'Connecting to Discord desktop…')
      this.tryPipe(0, ++this.generation)
    }
    if (this.pendingNonce && Date.now() - this.sentAt >= RETRY_MS) {
      this.disconnect('error', 'Discord did not acknowledge the presence update. Retrying…')
    } else this.flush()
  }

  private tryPipe(index: number, generation: number) {
    if (this.closed || generation !== this.generation) return
    if (index >= this.paths.length) {
      this.connecting = false
      this.nextAttempt = Date.now() + RETRY_MS
      this.onStatus('waiting-for-discord', 'Open Discord desktop. Peaks will reconnect automatically.')
      return
    }
    const socket = net.createConnection(this.paths[index])
    this.socket = socket
    socket.setTimeout(2000)
    let established = false
    const failed = () => {
      if (this.socket !== socket) return
      if (established) this.disconnect('waiting-for-discord', 'Discord disconnected. Peaks will reconnect automatically.')
      else {
        this.socket = null
        socket.destroy()
        this.tryPipe(index + 1, generation)
      }
    }
    socket.on('error', failed)
    socket.on('close', failed)
    socket.on('timeout', failed)
    socket.on('connect', () => {
      if (this.closed || generation !== this.generation) { socket.destroy(); return }
      established = true
      this.connecting = false
      socket.setTimeout(0)
      socket.write(encodeDiscordFrame(0, {v: 1, client_id: this.applicationId}))
      this.handshakeTimer = setTimeout(() => this.disconnect('error', 'Discord did not accept the connection. Check the Application ID.'), 5000)
      this.handshakeTimer.unref()
    })
    socket.on('data', data => {
      if (this.socket !== socket) return
      this.receive(Buffer.isBuffer(data) ? data : Buffer.from(data))
    })
  }

  private receive(data: Buffer) {
    this.buffer = Buffer.concat([this.buffer, data])
    if (this.buffer.length > MAX_FRAME_BYTES * 2) { this.disconnect('error', 'Discord sent an invalid response.'); return }
    while (this.buffer.length >= 8) {
      const opcode = this.buffer.readUInt32LE(0)
      const length = this.buffer.readUInt32LE(4)
      if (length > MAX_FRAME_BYTES) { this.disconnect('error', 'Discord sent an invalid response.'); return }
      if (this.buffer.length < 8 + length) return
      const raw = this.buffer.subarray(8, 8 + length)
      this.buffer = this.buffer.subarray(8 + length)
      if (opcode === 3) {
        const header = Buffer.alloc(8)
        header.writeUInt32LE(4, 0)
        header.writeUInt32LE(raw.length, 4)
        this.socket?.write(Buffer.concat([header, raw]))
        continue
      }
      if (opcode === 4) continue
      if (opcode === 2) { this.disconnect('error', 'Discord closed the connection. Check the Application ID.'); return }
      if (opcode !== 1) { this.disconnect('error', 'Discord sent an invalid response.'); return }
      let message: Record<string, unknown>
      try {
        const parsed: unknown = JSON.parse(raw.toString('utf8'))
        if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) throw new Error('Invalid frame')
        message = parsed as Record<string, unknown>
      } catch { this.disconnect('error', 'Discord sent an invalid response.'); return }
      // Never retain or log READY's Discord user identity or arbitrary error text.
      if (message.evt === 'ERROR') { this.disconnect('error', 'Discord rejected the presence. Check the Application ID and artwork assets.'); return }
      if (message.cmd === 'DISPATCH' && message.evt === 'READY') {
        clearTimeout(this.handshakeTimer)
        this.ready = true
        this.onStatus('connected', 'Connected to Discord desktop.')
        this.flush()
      } else if (message.cmd === 'SET_ACTIVITY' && message.nonce === this.pendingNonce) {
        this.pendingNonce = null
        // A new desired activity may still be waiting behind the update
        // cadence. Report the acknowledged frame, never the unsent request.
        this.onStatus('connected', this.sent !== 'null' ? 'Your current game activity is shared on Discord.' : 'Connected. Waiting for a supported game session.')
        this.flush()
      }
    }
  }

  private flush() {
    if (this.closed || !this.ready || !this.socket) return
    const key = JSON.stringify(this.desired)
    if (key === this.sent) return
    // Clearing for privacy/end-of-match bypasses the normal update cadence.
    if (this.desired !== null && (this.pendingNonce || Date.now() - this.sentAt < UPDATE_MS)) return
    this.pendingNonce = randomUUID()
    this.sent = key
    this.sentAt = Date.now()
    this.socket.write(encodeDiscordFrame(1, {cmd: 'SET_ACTIVITY', args: {pid: process.pid, activity: this.desired}, nonce: this.pendingNonce}))
  }

  private disconnect(status: DiscordConnectionStatus, detail: string) {
    clearTimeout(this.handshakeTimer)
    const socket = this.socket
    this.socket = null
    this.ready = false
    this.connecting = false
    this.buffer = Buffer.alloc(0)
    this.sent = undefined
    this.sentAt = 0
    this.pendingNonce = null
    this.nextAttempt = Date.now() + RETRY_MS
    this.generation++
    socket?.destroy()
    if (!this.closed) this.onStatus(status, detail)
  }

  dispose() {
    if (this.closed) return
    this.closed = true
    clearInterval(this.timer)
    clearTimeout(this.handshakeTimer)
    const socket = this.socket
    this.socket = null
    this.generation++
    if (this.ready && socket) {
      socket.end(encodeDiscordFrame(1, {cmd: 'SET_ACTIVITY', args: {pid: process.pid, activity: null}, nonce: randomUUID()}))
      const cleanup = setTimeout(() => socket.destroy(), 1000)
      cleanup.unref()
    } else socket?.destroy()
  }
}
