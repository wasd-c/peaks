import {pathToFileURL} from 'node:url'
import {describe, expect, it} from 'vitest'
import {
  decodePastedQrImagePayload,
  developmentRendererUrl,
  developmentServerUrl,
  isAllowedRendererUrl,
  isBackendCommand,
  isRiotClientWindowTitle,
} from './security'

describe('Electron privilege boundary', () => {
  const packaged = pathToFileURL('C:/Program Files/Peaks/resources/app.asar/dist/index.html').href

  it('allows only explicit backend commands', () => {
    expect(isBackendCommand('state')).toBe(true)
    expect(isBackendCommand('change_pin')).toBe(true)
    expect(isBackendCommand('confirm_totp_setup')).toBe(true)
    expect(isBackendCommand('connect_riot_client')).toBe(true)
    expect(isBackendCommand('connect_riot_qr_image')).toBe(true)
    expect(isBackendCommand('reset_application')).toBe(true)
    expect(isBackendCommand('toggle_watchlist')).toBe(true)
    expect(isBackendCommand('toggle_follow')).toBe(true)
    expect(isBackendCommand('scan_qr')).toBe(false)
    expect(isBackendCommand('read_file')).toBe(false)
    expect(isBackendCommand({command: 'state'})).toBe(false)
  })

  it('accepts only bounded canonical image payloads for pasted QR decoding', () => {
    const decoded = decodePastedQrImagePayload({
      encoding: 'image-base64',
      mimeType: 'image/png',
      bytes: 'AAEC/f7/',
    })
    expect([...decoded]).toEqual([0, 1, 2, 253, 254, 255])
    decoded.fill(0)

    expect(() => decodePastedQrImagePayload({
      encoding: 'image-base64',
      mimeType: 'image/svg+xml',
      bytes: 'AAEC',
    })).toThrow(/PNG/)
    expect(() => decodePastedQrImagePayload({
      encoding: 'image-base64',
      mimeType: 'image/png',
      bytes: 'not base64',
    })).toThrow(/invalid/)
  })

  it('targets only native Riot Client sign-in windows for QR capture', () => {
    expect(isRiotClientWindowTitle('Riot Client')).toBe(true)
    expect(isRiotClientWindowTitle(' Riot   Client Main ')).toBe(true)
    expect(isRiotClientWindowTitle('Riot Client — Sign in')).toBe(true)
    expect(isRiotClientWindowTitle('Riot Client help - Browser')).toBe(false)
    expect(isRiotClientWindowTitle('League of Legends')).toBe(false)
  })

  it('accepts only the configured development origin', () => {
    expect(isAllowedRendererUrl('http://localhost:5173/account', 'http://localhost:5173', packaged)).toBe(true)
    expect(isAllowedRendererUrl('https://example.com/', 'http://localhost:5173', packaged)).toBe(false)
    expect(isAllowedRendererUrl('http://localhost:5174/', 'http://localhost:5173', packaged)).toBe(false)
  })

  it('uses a loopback development server only in development', () => {
    expect(developmentServerUrl(false, 'http://localhost:5173/account')).toBe('http://localhost:5173')
    expect(developmentServerUrl(false, 'https://127.0.0.1:5173')).toBe('https://127.0.0.1:5173')
    expect(developmentServerUrl(false, 'https://example.com')).toBeUndefined()
    expect(developmentServerUrl(false, 'http://user@localhost:5173')).toBeUndefined()
    expect(developmentServerUrl(true, 'http://localhost:5173')).toBeUndefined()
  })

  it('adds the first-run route only for the explicit onboarding preview', () => {
    expect(developmentRendererUrl('http://localhost:5174', false)).toBe(
      'http://localhost:5174',
    )
    expect(developmentRendererUrl('http://localhost:5174', true)).toBe(
      'http://localhost:5174/?firstRun=1',
    )
    expect(developmentRendererUrl(undefined, true)).toBeUndefined()
  })

  it('accepts only the packaged renderer file outside development', () => {
    expect(isAllowedRendererUrl(`${packaged}#account`, undefined, packaged)).toBe(true)
    expect(isAllowedRendererUrl('https://example.com/', undefined, packaged)).toBe(false)
    expect(isAllowedRendererUrl('file:///C:/Temp/untrusted.html', undefined, packaged)).toBe(false)
  })
})
