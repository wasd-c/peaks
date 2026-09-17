interface ActivityHeartbeatOptions {
  canRefresh: () => boolean
  isBusy: () => boolean
  refresh: () => Promise<unknown>
}

/** Keep native activity fresh while Chromium throttles the background UI. */
export class DiscordActivityHeartbeat {
  private lastRequestAt = Date.now()
  private inFlight = false
  private disposed = false
  private timer: ReturnType<typeof setInterval>

  constructor(private options: ActivityHeartbeatOptions) {
    this.timer = setInterval(() => { void this.tick() }, 5000)
    this.timer.unref()
  }

  /** Renderer polls use the same clock, so foreground activity needs no extra polling. */
  noteActivityRequest() {
    this.lastRequestAt = Date.now()
  }

  private async tick() {
    if (this.disposed || this.inFlight || Date.now() - this.lastRequestAt < 20_000
      || !this.options.canRefresh() || this.options.isBusy()) return
    this.inFlight = true
    this.noteActivityRequest()
    try {
      await this.options.refresh()
    } catch {
      // The bridge records bounded diagnostics; the presence freshness
      // watchdog still clears independently when a refresh cannot complete.
    } finally { this.inFlight = false }
  }

  dispose() {
    this.disposed = true
    clearInterval(this.timer)
  }
}
