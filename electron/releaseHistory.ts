import {mkdirSync, readFileSync, renameSync, statSync, writeFileSync} from 'node:fs'
import path from 'node:path'
import type {ReleaseHistoryState} from './releaseHistoryTypes'

interface StoredHistory {version: string; previousVersion?: string; acknowledged: boolean}
const validVersion = (value: unknown): value is string => typeof value === 'string' && /^\d{1,4}\.\d{1,4}\.\d{1,4}$/.test(value)

export function isNewerVersion(current: string, previous: string): boolean {
  if (!validVersion(current) || !validVersion(previous)) return false
  const left = current.split('.').map(Number), right = previous.split('.').map(Number)
  for (let index = 0; index < 3; index++) {
    if (left[index] !== right[index]) return left[index] > right[index]
  }
  return false
}

/** Tracks installed versions independently of account data and renderer reloads. */
export class ReleaseHistory {
  private stored: StoredHistory

  constructor(private filename: string, private currentVersion: string, private enabled: boolean, existingInstallation = false) {
    let previous: StoredHistory | undefined
    if (enabled) {
      try {
        if (statSync(filename).size <= 1024) {
          const data = JSON.parse(readFileSync(filename, 'utf8'))
          if (validVersion(data.version) && typeof data.acknowledged === 'boolean') previous = {
            version: data.version, acknowledged: data.acknowledged,
            previousVersion: validVersion(data.previousVersion) ? data.previousVersion : undefined,
          }
        }
      } catch { /* Older installations predate this marker. */ }
    }
    this.stored = previous?.version === currentVersion ? previous
      : {version: currentVersion, previousVersion: previous?.version,
        acknowledged: previous ? !isNewerVersion(currentVersion, previous.version) : !existingInstallation}
    // Do not overwrite a newer baseline when the user temporarily runs an older build.
    if (enabled && (!previous || !isNewerVersion(previous.version, currentVersion))) {
      try { this.save(this.stored) } catch { /* Reading changelogs never blocks app startup. */ }
    }
  }

  snapshot(): ReleaseHistoryState {
    return {currentVersion: this.currentVersion, previousVersion: this.stored.previousVersion,
      pending: this.enabled && !this.stored.acknowledged}
  }

  handle(command: 'release_history' | 'release_history_ack', payload: unknown = {}): ReleaseHistoryState {
    if (!payload || typeof payload !== 'object' || Array.isArray(payload) || Object.keys(payload).length) throw new Error('Invalid changelog request')
    if (command === 'release_history_ack' && this.enabled && !this.stored.acknowledged) {
      const next = {...this.stored, acknowledged: true}
      try { this.save(next) } catch { throw new Error('Could not save the changelog preference. Try again.') }
      this.stored = next
    }
    return this.snapshot()
  }

  private save(value: StoredHistory) {
    mkdirSync(path.dirname(this.filename), {recursive: true})
    writeFileSync(`${this.filename}.tmp`, `${JSON.stringify(value)}\n`, {mode: 0o600})
    renameSync(`${this.filename}.tmp`, this.filename)
  }
}
