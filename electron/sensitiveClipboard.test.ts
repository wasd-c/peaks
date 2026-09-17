import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest'
import {createSensitiveClipboard} from './sensitiveClipboard'

function fixture() {
  let text = ''
  const clipboard = {
    writeText: vi.fn((value: string) => {text = value}),
    readText: vi.fn(() => text),
    clear: vi.fn(() => {text = ''}),
  }
  return {clipboard, sensitive: createSensitiveClipboard(clipboard)}
}

describe('sensitive clipboard lifecycle', () => {
  beforeEach(() => vi.useFakeTimers())
  afterEach(() => vi.useRealTimers())

  it('clears a copied code when the normal timeout expires', () => {
    const {clipboard, sensitive} = fixture()
    sensitive.copy('123456')
    vi.advanceTimersByTime(14_999)
    expect(clipboard.readText()).toBe('123456')
    vi.advanceTimersByTime(1)
    expect(clipboard.readText()).toBe('')
    expect(vi.getTimerCount()).toBe(0)
  })

  it('clears immediately on shutdown and cancels the pending timeout', () => {
    const {clipboard, sensitive} = fixture()
    sensitive.copy('123456')
    sensitive.dispose()
    expect(clipboard.readText()).toBe('')
    expect(vi.getTimerCount()).toBe(0)
    sensitive.dispose()
    expect(clipboard.clear).toHaveBeenCalledTimes(1)
  })

  it.each(['shutdown', 'timeout'])('preserves replacement clipboard content on %s', event => {
    const {clipboard, sensitive} = fixture()
    sensitive.copy('123456')
    clipboard.writeText('User copied something else')
    if (event === 'shutdown') sensitive.dispose()
    else vi.advanceTimersByTime(15_000)
    expect(clipboard.readText()).toBe('User copied something else')
    expect(clipboard.clear).not.toHaveBeenCalled()
  })

  it('replaces an older timeout when another code is copied', () => {
    const {clipboard, sensitive} = fixture()
    sensitive.copy('123456')
    vi.advanceTimersByTime(10_000)
    sensitive.copy('654321')
    vi.advanceTimersByTime(5_000)
    expect(clipboard.readText()).toBe('654321')
    vi.advanceTimersByTime(10_000)
    expect(clipboard.readText()).toBe('')
  })

  it('still clears the previous code if a later clipboard write fails', () => {
    const {clipboard, sensitive} = fixture()
    sensitive.copy('123456')
    clipboard.writeText.mockImplementationOnce(() => {throw new Error('Unavailable')})
    expect(() => sensitive.copy('654321')).toThrow('Unavailable')
    vi.advanceTimersByTime(15_000)
    expect(clipboard.readText()).toBe('')
  })

  it('allows shutdown to continue if the OS clipboard is unavailable', () => {
    const {clipboard, sensitive} = fixture()
    sensitive.copy('123456')
    clipboard.readText.mockImplementationOnce(() => {throw new Error('Unavailable')})
    expect(() => sensitive.dispose()).not.toThrow()
    expect(vi.getTimerCount()).toBe(0)
  })

  it('ignores a code returned by the backend after shutdown has started', () => {
    const {clipboard, sensitive} = fixture()
    sensitive.dispose()
    sensitive.copy('123456')
    expect(clipboard.writeText).not.toHaveBeenCalled()
    expect(vi.getTimerCount()).toBe(0)
  })
})
