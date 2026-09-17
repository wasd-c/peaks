import {EventEmitter} from 'node:events'
import {CancellationToken} from 'builder-util-runtime'
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest'
import type {UpdateInfo} from 'electron-updater'
import {PEAKS_RELEASE_PROVIDER, PeaksUpdater, validRelease} from './appUpdater'

const release = (): UpdateInfo => ({
  version: '0.4.0', releaseDate: '2026-09-18T12:00:00Z', path: 'Peaks-Setup-0.4.0.exe', sha512: Buffer.alloc(64, 1).toString('base64'),
  files: [{url: 'Peaks-Setup-0.4.0.exe', sha512: Buffer.alloc(64, 1).toString('base64'), size: 125_000_000}],
})

class Driver extends EventEmitter {
  autoDownload = true
  autoInstallOnAppQuit = true
  allowPrerelease = true
  allowDowngrade = true
  logger: unknown = console
  checkForUpdates = vi.fn(async () => { this.emit('update-available', release()); return {} })
  downloadUpdate = vi.fn(async (token: CancellationToken) => {
    if (token.cancelled) throw new Error('Download cancelled')
    this.emit('update-downloaded', release())
    return ['installer.exe']
  })
  quitAndInstall = vi.fn()
}

let driver: Driver
let updater: PeaksUpdater
let token: CancellationToken
const tick = async () => { for (let step = 0; step < 8; step++) await Promise.resolve() }

beforeEach(() => {
  vi.useFakeTimers()
  driver = new Driver()
  token = new CancellationToken()
  updater = new PeaksUpdater(driver, '0.3.0', () => token)
})
afterEach(() => { updater.dispose(); vi.useRealTimers() })

describe('Peaks release updates', () => {
  it('pins the public HTTPS repository and never enables unattended installation', () => {
    expect(PEAKS_RELEASE_PROVIDER).toEqual({provider: 'github', owner: 'wasd-c', repo: 'peaks', private: false, protocol: 'https'})
    expect(driver.autoDownload).toBe(false)
    expect(driver.autoInstallOnAppQuit).toBe(false)
    expect(driver.allowPrerelease).toBe(false)
    expect(driver.allowDowngrade).toBe(false)
    expect(driver.logger).toBeNull()
  })

  it('checks after startup and advertises availability without downloading', async () => {
    updater.start()
    updater.start()
    await vi.advanceTimersByTimeAsync(10_000)
    expect(driver.checkForUpdates).toHaveBeenCalledTimes(1)
    expect(updater.snapshot()).toMatchObject({phase: 'available', version: '0.4.0'})
    expect(driver.downloadUpdate).not.toHaveBeenCalled()
    expect(driver.quitAndInstall).not.toHaveBeenCalled()
  })

  it('rechecks periodically when up to date and deduplicates concurrent checks', async () => {
    driver.checkForUpdates.mockImplementation(async () => { driver.emit('update-not-available', release()); return {} })
    updater.start()
    await vi.advanceTimersByTimeAsync(10_000)
    await vi.advanceTimersByTimeAsync(6 * 60 * 60 * 1000)
    expect(driver.checkForUpdates).toHaveBeenCalledTimes(2)
    const first = updater.check()
    const second = updater.check()
    expect(first).toBe(second)
    await first
    expect(driver.checkForUpdates).toHaveBeenCalledTimes(3)
    expect(updater.snapshot().message).toBe('Peaks is up to date.')
  })

  it('uses one action to download and then silently install and restart', async () => {
    await updater.check()
    updater.install()
    updater.install()
    await tick()
    expect(driver.downloadUpdate).toHaveBeenCalledTimes(1)
    expect(driver.downloadUpdate).toHaveBeenCalledWith(token)
    expect(updater.snapshot().phase).toBe('ready')
    expect(driver.quitAndInstall).not.toHaveBeenCalled()
    await vi.advanceTimersByTimeAsync(800)
    expect(driver.quitAndInstall).toHaveBeenCalledExactlyOnceWith(true, true)
    expect(updater.snapshot().phase).toBe('installing')
  })

  it('never installs from an unsolicited downloaded event or absent release', async () => {
    driver.emit('update-downloaded', release())
    updater.install()
    await vi.advanceTimersByTimeAsync(1000)
    expect(driver.downloadUpdate).not.toHaveBeenCalled()
    expect(driver.quitAndInstall).not.toHaveBeenCalled()
  })

  it('reports bounded real download progress and never exposes installer paths', async () => {
    driver.downloadUpdate.mockImplementation(() => new Promise(() => undefined))
    await updater.check()
    updater.install()
    driver.emit('download-progress', {percent: 39.77, path: 'C:/private/user/file'})
    expect(updater.snapshot()).toMatchObject({phase: 'downloading', percent: 39})
    driver.emit('download-progress', {percent: Number.NaN})
    expect(updater.snapshot().percent).toBe(39)
    driver.emit('download-progress', {percent: 100.3})
    expect(updater.snapshot().percent).toBe(100)
    expect(JSON.stringify(updater.snapshot())).not.toContain('private')
  })

  it('retries failed downloads without requiring another availability check', async () => {
    await updater.check()
    driver.downloadUpdate.mockRejectedValueOnce(new Error('Authorization: secret; C:/private/file'))
    updater.install()
    await tick()
    expect(updater.snapshot()).toMatchObject({phase: 'error', retry: 'install', version: '0.4.0'})
    expect(JSON.stringify(updater.snapshot())).not.toMatch(/secret|private/)
    updater.install()
    await tick()
    await vi.advanceTimersByTimeAsync(800)
    expect(driver.downloadUpdate).toHaveBeenCalledTimes(2)
    expect(driver.quitAndInstall).toHaveBeenCalledTimes(1)
  })

  it('does not install when the downloaded version differs from the offered version', async () => {
    await updater.check()
    driver.downloadUpdate.mockImplementation(async () => { driver.emit('update-downloaded', {...release(), version: '0.2.0'}); return ['wrong.exe'] })
    updater.install()
    await tick()
    await vi.advanceTimersByTimeAsync(1000)
    expect(updater.snapshot().phase).toBe('error')
    expect(driver.quitAndInstall).not.toHaveBeenCalled()
  })

  it('times out and cancels a stalled download, ignoring subsequent progress', async () => {
    driver.downloadUpdate.mockImplementation(() => new Promise(() => undefined))
    await updater.check()
    updater.install()
    await vi.advanceTimersByTimeAsync(30 * 60 * 1000)
    expect(token.cancelled).toBe(true)
    expect(updater.snapshot()).toMatchObject({phase: 'error', retry: 'install'})
    driver.emit('download-progress', {percent: 100})
    driver.emit('update-downloaded', release())
    await vi.advanceTimersByTimeAsync(1000)
    expect(updater.snapshot().phase).toBe('error')
    expect(driver.quitAndInstall).not.toHaveBeenCalled()
  })

  it('keeps check failures generic and permits retry', async () => {
    driver.checkForUpdates.mockRejectedValueOnce(new Error('GET /releases token=private'))
    await updater.check()
    expect(updater.snapshot()).toMatchObject({phase: 'error', retry: 'check'})
    expect(updater.snapshot().message).not.toContain('private')
    await updater.check()
    expect(updater.snapshot().phase).toBe('available')
  })

  it('recovers from a synchronous installer failure without leaving an active download', async () => {
    await updater.check()
    driver.downloadUpdate.mockImplementationOnce(() => { throw new Error('Native failure') })
    updater.install()
    await tick()
    expect(updater.snapshot()).toMatchObject({phase: 'error', retry: 'install'})
    updater.install()
    await tick()
    await vi.advanceTimersByTimeAsync(800)
    expect(driver.quitAndInstall).toHaveBeenCalledTimes(1)
  })

  it('reports only state changes for diagnostics, not progress, URLs, or release details', async () => {
    updater.dispose()
    const changed = vi.fn()
    updater = new PeaksUpdater(driver, '0.3.0', () => token, changed)
    driver.downloadUpdate.mockImplementation(() => new Promise(() => undefined))
    await updater.check()
    updater.install()
    driver.emit('download-progress', {percent: 25})
    driver.emit('download-progress', {percent: 50})
    expect(changed.mock.calls).toEqual([['checking'], ['available'], ['downloading']])
  })

  it('rejects arbitrary payloads so renderer cannot supply a URL or install path', () => {
    for (const payload of [{url: 'https://evil.test/setup.exe'}, {token: 'secret'}, {path: 'setup.exe'}, null, [], true, '']) {
      expect(() => updater.handle('update_install', payload)).toThrow('Invalid update request')
    }
    expect(() => updater.handle('update_other', {})).toThrow('Unsupported update request')
    expect(updater.handle('update_status', {})).toEqual(updater.snapshot())
  })

  it('does nothing in development and cancels scheduled restart when disposed', async () => {
    const development = new PeaksUpdater(null, '0.3.0', () => token)
    development.start()
    expect((await development.check()).phase).toBe('unsupported')
    expect(development.install().phase).toBe('unsupported')
    development.dispose()
    await updater.check()
    updater.install()
    await tick()
    updater.dispose()
    await vi.advanceTimersByTimeAsync(1000)
    expect(driver.quitAndInstall).not.toHaveBeenCalled()
  })
})

describe('release metadata validation', () => {
  it('accepts generated NSIS release metadata', () => expect(validRelease(release())).toBe(true))
  it.each(['https://evil.test/setup.exe', '../setup.exe', 'setup.exe?token=abc', 'file:///C:/setup.exe', 'setup.msi', 'setup.exe\n'])('rejects unsafe or unsupported installer %s', url => {
    expect(validRelease({...release(), files: [{...release().files[0], url}]})).toBe(false)
  })
  it.each(['0.4.0-beta.1', 'v0.4.0', '01.4.0', '0.4.0<script>', '0.4.0\n'])('rejects non-stable version %s', version => {
    expect(validRelease({...release(), version})).toBe(false)
  })
  it('rejects absent checksums, missing installers, and excessive downloads', () => {
    expect(validRelease({...release(), files: []})).toBe(false)
    expect(validRelease({...release(), files: [{...release().files[0], sha512: 'nope'}]})).toBe(false)
    expect(validRelease({...release(), files: [{...release().files[0], size: 3_000_000_000}]})).toBe(false)
  })
})
