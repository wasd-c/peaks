import {Buffer} from 'node:buffer'

export const BACKEND_COMMANDS = new Set([
  'activity',
  'add_account',
  'api_key',
  'cancel_totp_setup',
  'change_pin',
  'confirm_totp_setup',
  'connect_riot_client',
  'connect_riot_qr_image',
  'copy_totp',
  'import_session',
  'lock',
  'pin',
  'prepare_totp_setup',
  'refresh',
  'remove_account',
  'reset_application',
  'search',
  'settings',
  'state',
  'toggle_follow',
  'toggle_watchlist',
])

export const MAX_PASTED_QR_IMAGE_BYTES = 8 * 1024 * 1024

/** Match posters accept bounded PNGs only, validated before native decoding. */
export function decodeMatchImagePayload(value: unknown): Buffer {
  const dataUrl = value && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>).dataUrl : undefined
  const prefix = 'data:image/png;base64,'
  if (typeof dataUrl !== 'string' || !dataUrl.startsWith(prefix)) {
    throw new Error('The match image must be a PNG')
  }
  const encoded = dataUrl.slice(prefix.length)
  if (!encoded || encoded.length > Math.ceil(MAX_PASTED_QR_IMAGE_BYTES / 3) * 4
    || encoded.length % 4 !== 0 || !/^[A-Za-z0-9+/]*={0,2}$/.test(encoded)) {
    throw new Error('The match image is invalid or too large')
  }
  const bytes = Buffer.from(encoded, 'base64')
  if (bytes.length < 24 || bytes.length > MAX_PASTED_QR_IMAGE_BYTES
    || bytes.toString('base64') !== encoded
    || !bytes.subarray(0, 8).equals(Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]))
    || bytes.toString('ascii', 12, 16) !== 'IHDR') {
    throw new Error('The match image is not a valid PNG')
  }
  const width = bytes.readUInt32BE(16), height = bytes.readUInt32BE(20)
  if (!width || !height || width > 2400 || height > 2400) {
    throw new Error('The match image dimensions are too large')
  }
  return bytes
}

const PASTED_QR_IMAGE_TYPES = new Set([
  'image/bmp',
  'image/jpeg',
  'image/png',
  'image/webp',
])

interface PastedQrImagePayload {
  encoding: 'image-base64'
  mimeType: string
  bytes: string
}

/** Validate and decode renderer-provided image bytes before native parsing. */
export function decodePastedQrImagePayload(value: unknown): Buffer {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error('Choose a PNG, JPEG, WebP, or BMP QR image')
  }
  const candidate = value as Partial<PastedQrImagePayload>
  if (
    candidate.encoding !== 'image-base64'
    || typeof candidate.mimeType !== 'string'
    || !PASTED_QR_IMAGE_TYPES.has(candidate.mimeType.toLowerCase())
  ) {
    throw new Error('Choose a PNG, JPEG, WebP, or BMP QR image')
  }
  const encoded = candidate.bytes
  const maxEncodedLength = Math.ceil(MAX_PASTED_QR_IMAGE_BYTES / 3) * 4
  if (
    typeof encoded !== 'string'
    || encoded.length === 0
    || encoded.length > maxEncodedLength
    || encoded.length % 4 !== 0
    || !/^[A-Za-z0-9+/]*={0,2}$/.test(encoded)
  ) {
    throw new Error('The QR image data is invalid')
  }

  const decoded = Buffer.from(encoded, 'base64')
  if (decoded.length === 0 || decoded.length > MAX_PASTED_QR_IMAGE_BYTES) {
    decoded.fill(0)
    throw new Error('The QR image is too large; choose an image under 8 MB')
  }
  if (decoded.toString('base64') !== encoded) {
    decoded.fill(0)
    throw new Error('The QR image data is invalid')
  }
  return decoded
}

export function isBackendCommand(value: unknown): value is string {
  return typeof value === 'string' && BACKEND_COMMANDS.has(value)
}

/** Match only Riot Client windows that can contain the native QR sign-in. */
export function isRiotClientWindowTitle(value: string): boolean {
  const title = value.trim().replace(/\s+/g, ' ').toLocaleLowerCase()
  return title === 'riot client'
    || title === 'riot client main'
    || /^riot client\s*[—-]\s*(?:sign in|log in|login|authentication)$/.test(title)
}

export function developmentServerUrl(
  isPackaged: boolean,
  candidate: string | undefined,
): string | undefined {
  if (isPackaged || !candidate) return undefined

  try {
    const parsed = new URL(candidate)
    const loopbackHosts = new Set(['localhost', '127.0.0.1', '[::1]'])
    if (
      !['http:', 'https:'].includes(parsed.protocol)
      || !loopbackHosts.has(parsed.hostname)
      || parsed.username
      || parsed.password
    ) return undefined
    return parsed.origin
  } catch {
    return undefined
  }
}

/** Add the renderer-only first-run route to an already validated dev origin. */
export function developmentRendererUrl(
  devServerUrl: string | undefined,
  onboardingPreview: boolean,
): string | undefined {
  if (!devServerUrl || !onboardingPreview) return devServerUrl
  const rendererUrl = new URL(devServerUrl)
  rendererUrl.searchParams.set('firstRun', '1')
  return rendererUrl.href
}

export function isAllowedRendererUrl(
  candidate: string,
  devServerUrl: string | undefined,
  packagedRendererUrl: string,
): boolean {
  try {
    const actual = new URL(candidate)
    if (devServerUrl) return actual.origin === new URL(devServerUrl).origin

    const expected = new URL(packagedRendererUrl)
    actual.hash = ''
    actual.search = ''
    expected.hash = ''
    expected.search = ''
    return actual.href === expected.href
  } catch {
    return false
  }
}
