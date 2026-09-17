import {Buffer} from 'node:buffer'
import {describe, expect, it} from 'vitest'
import {decodeMatchImagePayload, isBackendCommand} from './security'

const pixel = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Wl2nS8AAAAASUVORK5CYII='
describe('native match image boundary', () => {
  it('accepts a bounded PNG without exposing a new backend command', () => {
    expect(decodeMatchImagePayload({dataUrl: `data:image/png;base64,${pixel}`})).toEqual(Buffer.from(pixel, 'base64'))
    expect(isBackendCommand('copy_match_image')).toBe(false)
  })
  it('rejects non-images, alternate media and malformed base64', () => {
    for (const dataUrl of ['https://example.com/a.png', 'data:image/svg+xml;base64,AAAA', 'data:image/png;base64,bad', 'data:image/png;base64,YWFhYQ==']) {
      expect(() => decodeMatchImagePayload({dataUrl})).toThrow()
    }
  })
  it('rejects oversized dimensions before invoking a native image decoder', () => {
    const bytes = Buffer.from(pixel, 'base64')
    bytes.writeUInt32BE(100000, 16)
    expect(() => decodeMatchImagePayload({dataUrl: `data:image/png;base64,${bytes.toString('base64')}`})).toThrow(/dimensions/)
  })
})
