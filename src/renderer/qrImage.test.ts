import {describe, expect, it} from 'vitest'
import {
  encodeQrImage,
  QR_IMAGE_MAX_BYTES,
  qrImageValidationError,
} from './qrImage'

describe('pasted QR image preparation', () => {
  it('encodes an accepted image without adding a data URL prefix', async () => {
    const file = {
      arrayBuffer: async () => Uint8Array.from([0, 1, 2, 253, 254, 255]).buffer,
      size: 6,
      type: 'image/png',
    } as File

    await expect(encodeQrImage(file)).resolves.toEqual({
      qrImage: {
        encoding: 'image-base64',
        mimeType: 'image/png',
        bytes: 'AAEC/f7/',
      },
    })
  })

  it('rejects unsupported, empty, and oversized files before reading them', () => {
    expect(qrImageValidationError({size: 1, type: 'image/svg+xml'})).toContain('PNG')
    expect(qrImageValidationError({size: 0, type: 'image/png'})).toContain('empty')
    expect(qrImageValidationError({
      size: QR_IMAGE_MAX_BYTES + 1,
      type: 'image/jpeg',
    })).toContain('under 8 MB')
  })
})
