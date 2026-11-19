import {readFileSync, writeFileSync} from 'node:fs'

export interface WindowBehavior {
  minimizeOnClose: boolean
}

export function readWindowBehavior(filename: string): WindowBehavior {
  try {
    const saved: unknown = JSON.parse(readFileSync(filename, 'utf8'))
    if (saved && typeof saved === 'object' && 'minimizeOnClose' in saved
      && typeof saved.minimizeOnClose === 'boolean') {
      return {minimizeOnClose: saved.minimizeOnClose}
    }
  } catch { /* A missing or malformed preference uses the default. */ }
  return {minimizeOnClose: true}
}

export function writeWindowBehavior(filename: string, value: unknown): WindowBehavior {
  if (!value || typeof value !== 'object' || !('minimizeOnClose' in value)
    || typeof value.minimizeOnClose !== 'boolean') {
    throw new TypeError('Choose a valid window behavior')
  }
  const behavior = {minimizeOnClose: value.minimizeOnClose}
  writeFileSync(filename, JSON.stringify(behavior), {encoding: 'utf8', mode: 0o600})
  return behavior
}
