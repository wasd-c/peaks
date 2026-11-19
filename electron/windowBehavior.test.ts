import {mkdtempSync, readFileSync, rmdirSync, unlinkSync, writeFileSync} from 'node:fs'
import {tmpdir} from 'node:os'
import path from 'node:path'
import {describe, expect, it} from 'vitest'
import {readWindowBehavior, writeWindowBehavior} from './windowBehavior'

describe('window close preference', () => {
  it('defaults to the tray and preserves an explicit quit-on-close choice', () => {
    const directory = mkdtempSync(path.join(tmpdir(), 'peaks-window-behavior-'))
    const filename = path.join(directory, 'window-behavior.json')
    try {
      expect(readWindowBehavior(filename)).toEqual({minimizeOnClose: true})
      expect(writeWindowBehavior(filename, {minimizeOnClose: false})).toEqual({minimizeOnClose: false})
      expect(readWindowBehavior(filename)).toEqual({minimizeOnClose: false})
      expect(JSON.parse(readFileSync(filename, 'utf8'))).toEqual({minimizeOnClose: false})
      expect(() => writeWindowBehavior(filename, {minimizeOnClose: 'false'})).toThrow()
      writeFileSync(filename, '{broken')
      expect(readWindowBehavior(filename)).toEqual({minimizeOnClose: true})
    } finally {
      unlinkSync(filename)
      rmdirSync(directory)
    }
  })
})
