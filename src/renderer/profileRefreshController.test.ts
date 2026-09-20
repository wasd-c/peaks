import {describe, expect, it, vi} from 'vitest'
import {createProfileRefreshController} from './profileRefreshController'

function deferred() {
  let resolve!: () => void
  let reject!: (error: unknown) => void
  const promise = new Promise<void>((ok, fail) => { resolve = ok; reject = fail })
  return {promise, resolve, reject}
}

describe('account profile refresh failure handling', () => {
  it('contains an actual rejected bridge request and leaves a retry available', async () => {
    const onPhase = vi.fn(), onSuccess = vi.fn()
    const request = vi.fn<() => Promise<void>>().mockRejectedValueOnce(new Error('VALORANT is not active')).mockResolvedValueOnce(undefined)
    const controller = createProfileRefreshController({request, onPhase, onSuccess})
    await expect(controller.refresh()).resolves.toBeUndefined()
    expect(onPhase.mock.calls.map(call => call[0])).toEqual(['pending', 'failed'])
    expect(onSuccess).not.toHaveBeenCalled()
    await expect(controller.refresh()).resolves.toBeUndefined()
    expect(onPhase.mock.calls.map(call => call[0])).toEqual(['pending', 'failed', 'pending', 'idle'])
    expect(onSuccess).toHaveBeenCalledOnce()
  })

  it('also contains a synchronous rejection from the refresh callback', async () => {
    const onPhase = vi.fn(), onSuccess = vi.fn()
    const controller = createProfileRefreshController({request: () => { throw new Error('Service unavailable') }, onPhase, onSuccess})
    await expect(controller.refresh()).resolves.toBeUndefined()
    expect(onPhase).toHaveBeenLastCalledWith('failed')
    expect(onSuccess).not.toHaveBeenCalled()
  })

  it('deduplicates clicks while a request is pending and increments only on success', async () => {
    const result = deferred(), onPhase = vi.fn(), onSuccess = vi.fn(), request = vi.fn(() => result.promise)
    const controller = createProfileRefreshController({request, onPhase, onSuccess})
    const first = controller.refresh(), second = controller.refresh()
    expect(first).toBe(second)
    expect(request).toHaveBeenCalledOnce()
    result.resolve()
    await first
    expect(onSuccess).toHaveBeenCalledOnce()
    expect(onPhase.mock.calls.map(call => call[0])).toEqual(['pending', 'idle'])
  })

  it.each(['resolve', 'reject'] as const)('ignores a late %s after navigation or unmount', async outcome => {
    const result = deferred(), onPhase = vi.fn(), onSuccess = vi.fn(), request = vi.fn(() => result.promise)
    const old = createProfileRefreshController({request, onPhase, onSuccess})
    const running = old.refresh()
    old.dispose()
    if (outcome === 'resolve') result.resolve()
    else result.reject(new Error('Late failure from previous profile'))
    await expect(running).resolves.toBeUndefined()
    expect(onPhase.mock.calls.map(call => call[0])).toEqual(['pending'])
    expect(onSuccess).not.toHaveBeenCalled()
    await old.refresh()
    expect(request).toHaveBeenCalledOnce()
  })

  it('keeps a new profile independent from an earlier disposed request', async () => {
    const previous = deferred(), oldSuccess = vi.fn(), newSuccess = vi.fn(), oldPhase = vi.fn(), newPhase = vi.fn()
    const first = createProfileRefreshController({request: () => previous.promise, onPhase: oldPhase, onSuccess: oldSuccess})
    const oldRun = first.refresh()
    first.dispose()
    const second = createProfileRefreshController({request: async () => undefined, onPhase: newPhase, onSuccess: newSuccess})
    await second.refresh()
    previous.reject(new Error('Old profile unavailable'))
    await oldRun
    expect(oldSuccess).not.toHaveBeenCalled()
    expect(oldPhase.mock.calls.map(call => call[0])).toEqual(['pending'])
    expect(newSuccess).toHaveBeenCalledOnce()
    expect(newPhase.mock.calls.map(call => call[0])).toEqual(['pending', 'idle'])
  })
})
