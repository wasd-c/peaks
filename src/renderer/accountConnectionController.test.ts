import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest'
import {createAccountConnectionController} from './accountConnectionController'

function deferred() {
  let resolve!: () => void
  let reject!: (error: unknown) => void
  const promise = new Promise<void>((done, fail) => {resolve = done; reject = fail})
  return {promise, resolve, reject}
}

function setup(approve = vi.fn<(_: string) => Promise<void>>().mockResolvedValue(undefined)) {
  const onChange = vi.fn()
  const onError = vi.fn()
  return {approve, onChange, onError, ...createAccountConnectionController({approve, onChange, onError})}
}

describe('account connection approval lifecycle', () => {
  beforeEach(() => vi.useFakeTimers())
  afterEach(() => vi.useRealTimers())

  it('stays pending until Riot approves, then shows the check before fading back to idle', async () => {
    const approval = deferred()
    const connection = setup(vi.fn().mockReturnValue(approval.promise))
    const request = connection.connect('selected-account')
    expect(connection.onChange.mock.calls).toEqual([[{accountId: 'selected-account', phase: 'pending'}]])
    await vi.advanceTimersByTimeAsync(60_000)
    expect(connection.onChange).toHaveBeenCalledTimes(1)
    expect(vi.getTimerCount()).toBe(0)

    approval.resolve()
    await request
    expect(connection.onChange).toHaveBeenLastCalledWith({accountId: 'selected-account', phase: 'approved'})
    await vi.advanceTimersByTimeAsync(799)
    expect(connection.onChange).toHaveBeenCalledTimes(2)
    await vi.advanceTimersByTimeAsync(1)
    expect(connection.onChange).toHaveBeenLastCalledWith({accountId: 'selected-account', phase: 'leaving'})
    await vi.advanceTimersByTimeAsync(649)
    expect(connection.onChange).toHaveBeenCalledTimes(3)
    await vi.advanceTimersByTimeAsync(1)
    expect(connection.onChange).toHaveBeenLastCalledWith(null)
    expect(connection.onError).not.toHaveBeenCalled()
    expect(vi.getTimerCount()).toBe(0)
  })

  it('reports failure without a false success check and immediately permits retry', async () => {
    const error = new Error('No readable Riot sign-in QR')
    const connection = setup(vi.fn().mockRejectedValueOnce(error).mockResolvedValue(undefined))
    await connection.connect('selected-account')
    expect(connection.onChange.mock.calls).toEqual([
      [{accountId: 'selected-account', phase: 'pending'}], [null],
    ])
    expect(connection.onError).toHaveBeenCalledExactlyOnceWith(error)
    expect(vi.getTimerCount()).toBe(0)
    await connection.connect('selected-account')
    expect(connection.approve).toHaveBeenCalledTimes(2)
    expect(connection.onChange).toHaveBeenLastCalledWith({accountId: 'selected-account', phase: 'approved'})
    connection.dispose()
  })

  it('ignores additional Use actions until approval and the completion animation are finished', async () => {
    const approval = deferred()
    const connection = setup(vi.fn().mockReturnValueOnce(approval.promise).mockResolvedValue(undefined))
    const first = connection.connect('first-account')
    await connection.connect('second-account')
    await connection.connect('first-account')
    expect(connection.approve).toHaveBeenCalledExactlyOnceWith('first-account')
    approval.resolve()
    await first
    await connection.connect('second-account')
    await vi.advanceTimersByTimeAsync(800)
    await connection.connect('second-account')
    expect(connection.approve).toHaveBeenCalledTimes(1)
    await vi.advanceTimersByTimeAsync(650)
    await connection.connect('second-account')
    expect(connection.approve.mock.calls).toEqual([['first-account'], ['second-account']])
    expect(connection.onChange).toHaveBeenLastCalledWith({accountId: 'second-account', phase: 'approved'})
    connection.dispose()
  })

  it.each(['resolve', 'reject'] as const)('drops a late approval %s after disposal', async outcome => {
    const approval = deferred()
    const connection = setup(vi.fn().mockReturnValue(approval.promise))
    const request = connection.connect('selected-account')
    connection.dispose()
    if (outcome === 'resolve') approval.resolve()
    else approval.reject(new Error('Late approval failure'))
    await request
    await vi.runAllTimersAsync()
    await connection.connect('another-account')
    expect(connection.onChange.mock.calls).toEqual([[{accountId: 'selected-account', phase: 'pending'}]])
    expect(connection.onError).not.toHaveBeenCalled()
    expect(connection.approve).toHaveBeenCalledTimes(1)
    expect(vi.getTimerCount()).toBe(0)
  })

  it.each([0, 800])('cancels completion timers when disposed after %i ms', async elapsed => {
    const connection = setup()
    await connection.connect('selected-account')
    if (elapsed) await vi.advanceTimersByTimeAsync(elapsed)
    const callsBeforeDisposal = connection.onChange.mock.calls.length
    expect(vi.getTimerCount()).toBe(1)
    connection.dispose()
    connection.dispose()
    expect(vi.getTimerCount()).toBe(0)
    await vi.runAllTimersAsync()
    expect(connection.onChange).toHaveBeenCalledTimes(callsBeforeDisposal)
    expect(connection.onError).not.toHaveBeenCalled()
  })

  it('handles a synchronous approval failure just like a rejected request', async () => {
    const error = new Error('Bridge unavailable')
    const connection = setup(vi.fn(() => {throw error}))
    await connection.connect('selected-account')
    expect(connection.onError).toHaveBeenCalledExactlyOnceWith(error)
    expect(connection.onChange.mock.calls).toEqual([
      [{accountId: 'selected-account', phase: 'pending'}], [null],
    ])
    expect(vi.getTimerCount()).toBe(0)
  })
})
