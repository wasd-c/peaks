import type {Settings} from './types'

export type AutoLockReason = 'inactivity' | 'manual'

const MILLISECONDS_PER_MINUTE = 60_000

const AUTO_LOCK_PAUSED_COMMANDS = new Set([
  'add_account',
  'change_pin',
  'confirm_totp_setup',
  'connect_riot_client',
  'connect_riot_qr_image',
  'import_session',
  'prepare_totp_setup',
])

export function pausesAutoLock(command: string): boolean {
  return AUTO_LOCK_PAUSED_COMMANDS.has(command)
}

function inactivityDelay(settings: Pick<Settings, 'autoLockMinutes'>): number | null {
  const minutes = settings.autoLockMinutes
  if (!Number.isFinite(minutes) || minutes <= 0) return null
  return minutes * MILLISECONDS_PER_MINUTE
}

export class AutoLockCoordinator {
  private lastActivityAt: number
  private pauseCount = 0
  private lockPending = false

  constructor(now: number) {
    this.lastActivityAt = now
  }

  get isPaused(): boolean {
    return this.pauseCount > 0
  }

  get hasLockPending(): boolean {
    return this.lockPending
  }

  recordActivity(now: number): void {
    this.lastActivityAt = now
  }

  pause(): (now: number) => void {
    this.pauseCount += 1
    let resumed = false

    return (now: number) => {
      if (resumed) return
      resumed = true
      this.pauseCount = Math.max(0, this.pauseCount - 1)
      this.recordActivity(now)
    }
  }

  tryBeginLock(
    reason: AutoLockReason,
    settings: Pick<Settings, 'autoLockMinutes'>,
    now: number,
  ): boolean {
    if (this.lockPending) return false
    if (this.isPaused) return false

    if (reason === 'inactivity') {
      const delay = inactivityDelay(settings)
      if (delay === null || now - this.lastActivityAt < delay) return false
    }

    this.lockPending = true
    return true
  }

  releaseFailedLock(now: number): void {
    this.lockPending = false
    this.recordActivity(now)
  }
}
