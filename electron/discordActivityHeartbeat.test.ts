import {afterEach, describe, expect, it, vi} from 'vitest'
import {DiscordActivityHeartbeat} from './discordActivityHeartbeat'

const schedulers: DiscordActivityHeartbeat[] = []
function setup() {
  vi.useFakeTimers()
  const options = {canRefresh: vi.fn(() => true), isBusy: vi.fn(() => false), refresh: vi.fn<() => Promise<unknown>>().mockResolvedValue(undefined)}
  const scheduler = new DiscordActivityHeartbeat(options)
  schedulers.push(scheduler)
  return {scheduler, ...options}
}
afterEach(() => {
  schedulers.splice(0).forEach(scheduler => scheduler.dispose())
  vi.useRealTimers()
})

describe('native Discord activity heartbeat', () => {
  it('refreshes every twenty seconds when the renderer is throttled', async () => {
    const {refresh} = setup()
    await vi.advanceTimersByTimeAsync(19_999)
    expect(refresh).not.toHaveBeenCalled()
    await vi.advanceTimersByTimeAsync(20_001)
    expect(refresh).toHaveBeenCalledTimes(2)
  })

  it('does no extra work while normal renderer polls remain timely', async () => {
    const {scheduler, refresh} = setup()
    for (let index = 0; index < 8; index++) {
      await vi.advanceTimersByTimeAsync(15_000)
      scheduler.noteActivityRequest()
    }
    expect(refresh).not.toHaveBeenCalled()
  })

  it('waits for other bridge work and never overlaps a pending refresh', async () => {
    const {refresh, isBusy} = setup()
    isBusy.mockReturnValue(true)
    await vi.advanceTimersByTimeAsync(60_000)
    expect(refresh).not.toHaveBeenCalled()
    isBusy.mockReturnValue(false)
    let finish!: () => void
    refresh.mockImplementationOnce(() => new Promise<void>(resolve => { finish = resolve }))
    await vi.advanceTimersByTimeAsync(65_000)
    expect(refresh).toHaveBeenCalledOnce()
    finish()
    await vi.advanceTimersByTimeAsync(5000)
    expect(refresh).toHaveBeenCalledTimes(2)
  })

  it('honors privacy immediately and stops after disposal', async () => {
    const {scheduler, canRefresh, refresh} = setup()
    canRefresh.mockReturnValue(false)
    await vi.advanceTimersByTimeAsync(65_000)
    expect(refresh).not.toHaveBeenCalled()
    canRefresh.mockReturnValue(true)
    await vi.advanceTimersByTimeAsync(5000)
    expect(refresh).toHaveBeenCalledOnce()
    scheduler.dispose()
    await vi.advanceTimersByTimeAsync(65_000)
    expect(refresh).toHaveBeenCalledOnce()
  })

  it('backs off errors without unhandled rejection or an unbounded request loop', async () => {
    const {refresh} = setup()
    refresh.mockRejectedValue(new Error('Backend unavailable'))
    await vi.advanceTimersByTimeAsync(65_000)
    expect(refresh).toHaveBeenCalledTimes(3)
  })
})
