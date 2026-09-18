import {mkdtempSync, readFileSync, rmSync, writeFileSync} from 'node:fs'
import {tmpdir} from 'node:os'
import path from 'node:path'
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest'
import {ReleaseHistory, isNewerVersion} from './releaseHistory'

const disk = vi.hoisted(() => ({fail: false}))
vi.mock('node:fs', async importOriginal => {
  const actual = await importOriginal<typeof import('node:fs')>()
  return {...actual, renameSync: (...args: Parameters<typeof actual.renameSync>) => {
    if (disk.fail) throw new Error('disk unavailable')
    return actual.renameSync(...args)
  }}
})

let directory: string, filename: string
beforeEach(() => {
  disk.fail = false
  directory = mkdtempSync(path.join(tmpdir(), 'peaks-release-history-'))
  filename = path.join(directory, 'release-history.json')
})
afterEach(() => {
  const resolved = path.resolve(directory)
  if (path.dirname(resolved) !== path.resolve(tmpdir()) || !path.basename(resolved).startsWith('peaks-release-history-')) throw new Error('Unsafe temporary test path')
  rmSync(resolved, {recursive: true, force: true})
})

describe('installed release changelogs', () => {
  it('does not interrupt a first install, but detects the next installed version', () => {
    expect(new ReleaseHistory(filename, '0.3.1', true).snapshot().pending).toBe(false)
    expect(new ReleaseHistory(filename, '0.4.0', true).snapshot()).toEqual({currentVersion: '0.4.0', previousVersion: '0.3.1', pending: true})
  })
  it('retains unread notes across restarts and acknowledges them only once', () => {
    new ReleaseHistory(filename, '0.3.1', true)
    new ReleaseHistory(filename, '0.4.0', true)
    const restarted = new ReleaseHistory(filename, '0.4.0', true)
    expect(restarted.snapshot().pending).toBe(true)
    expect(restarted.handle('release_history').pending).toBe(true)
    expect(restarted.handle('release_history_ack').pending).toBe(false)
    expect(restarted.handle('release_history_ack').pending).toBe(false)
    expect(new ReleaseHistory(filename, '0.4.0', true).snapshot().pending).toBe(false)
    expect(new ReleaseHistory(filename, '0.4.1', true).snapshot().pending).toBe(true)
  })
  it('shows notes once when an existing installation predates the version marker', () => {
    const migrated = new ReleaseHistory(filename, '0.4.0', true, true)
    expect(migrated.snapshot()).toEqual({currentVersion: '0.4.0', previousVersion: undefined, pending: true})
    migrated.handle('release_history_ack')
    expect(new ReleaseHistory(filename, '0.4.0', true, true).snapshot().pending).toBe(false)
  })
  it('compares numeric versions, handles skipped releases and ignores downgrades', () => {
    expect(isNewerVersion('0.10.0', '0.9.9')).toBe(true)
    expect(isNewerVersion('1.0.0', '0.99.99')).toBe(true)
    expect(isNewerVersion('0.3.1', '0.3.1')).toBe(false)
    expect(isNewerVersion('invalid', '0.3.1')).toBe(false)
    new ReleaseHistory(filename, '0.9.9', true)
    new ReleaseHistory(filename, '0.10.0', true).handle('release_history_ack')
    const stored = readFileSync(filename, 'utf8')
    expect(new ReleaseHistory(filename, '0.3.1', true).snapshot().pending).toBe(false)
    expect(readFileSync(filename, 'utf8')).toBe(stored)
    expect(new ReleaseHistory(filename, '0.10.0', true).snapshot().pending).toBe(false)
  })
  it('does not let development or demo runs consume the installed app changelog', () => {
    new ReleaseHistory(filename, '0.3.1', true)
    new ReleaseHistory(filename, '0.4.0', true)
    const stored = readFileSync(filename, 'utf8')
    const development = new ReleaseHistory(filename, '0.4.0', false)
    expect(development.handle('release_history_ack').pending).toBe(false)
    expect(readFileSync(filename, 'utf8')).toBe(stored)
    expect(new ReleaseHistory(filename, '0.4.0', true).snapshot().pending).toBe(true)
  })
  it('keeps notes pending if acknowledgement cannot be saved', () => {
    new ReleaseHistory(filename, '0.3.1', true)
    const release = new ReleaseHistory(filename, '0.4.0', true)
    disk.fail = true
    expect(() => release.handle('release_history_ack')).toThrow('Could not save the changelog preference')
    expect(release.snapshot().pending).toBe(true)
    disk.fail = false
    expect(release.handle('release_history_ack').pending).toBe(false)
  })
  it('recovers safely from corrupt or oversized markers and rejects unexpected IPC fields', () => {
    for (const contents of ['null', '{broken', 'a'.repeat(1025), '{"version":"invalid","acknowledged":false}']) {
      writeFileSync(filename, contents)
      expect(new ReleaseHistory(filename, '0.3.1', true).snapshot().pending).toBe(false)
    }
    const release = new ReleaseHistory(filename, '0.4.0', true)
    for (const input of [null, [], '0.4.0', {version: '9.9.9'}]) expect(() => release.handle('release_history_ack', input)).toThrow('Invalid changelog request')
    expect(release.snapshot().pending).toBe(true)
  })
})
