export const QR_IMAGE_ACCEPT = 'image/png,image/jpeg,image/webp,image/bmp'
export const QR_IMAGE_MAX_BYTES = 8 * 1024 * 1024

const QR_IMAGE_TYPES = new Set(QR_IMAGE_ACCEPT.split(','))

export interface QrImageRequest {
  qrImage: {
    encoding: 'image-base64'
    mimeType: string
    bytes: string
  }
}

export function qrImageValidationError(file: Pick<File, 'size' | 'type'> | null): string {
  if (!file) return 'Choose or paste a QR image'
  if (!QR_IMAGE_TYPES.has(file.type.toLowerCase())) {
    return 'Choose a PNG, JPEG, WebP, or BMP image'
  }
  if (file.size <= 0) return 'The selected image is empty'
  if (file.size > QR_IMAGE_MAX_BYTES) return 'Choose an image under 8 MB'
  return ''
}

function bytesToBase64(bytes: Uint8Array): string {
  const chunks: string[] = []
  for (let offset = 0; offset < bytes.length; offset += 32_768) {
    chunks.push(String.fromCharCode(...bytes.subarray(offset, offset + 32_768)))
  }
  return btoa(chunks.join(''))
}

export async function encodeQrImage(file: File): Promise<QrImageRequest> {
  const validationError = qrImageValidationError(file)
  if (validationError) throw new Error(validationError)

  const buffer = await file.arrayBuffer()
  if (buffer.byteLength !== file.size || buffer.byteLength > QR_IMAGE_MAX_BYTES) {
    throw new Error('The QR image changed while it was being read; choose it again')
  }
  return {
    qrImage: {
      encoding: 'image-base64',
      mimeType: file.type.toLowerCase(),
      bytes: bytesToBase64(new Uint8Array(buffer)),
    },
  }
}
