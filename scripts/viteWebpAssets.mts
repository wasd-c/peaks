import path from 'node:path'
import sharp from 'sharp'
import type { Plugin } from 'vite'

export interface WebpAssetsOptions {
  /** Longest edge kept in the packaged image. The Valorant map art ships at 4K. */
  maxDimension?: number
  quality?: number
  /** Assets below this size are left as PNG; re-encoding them saves little. */
  minBytes?: number
}

/**
 * Re-encode bundled PNG assets as WebP at build time.
 *
 * Source art stays PNG because the Python UI and `scripts/fetch_assets.py`
 * read it by path. Only the packaged renderer output is converted, and every
 * reference to a renamed file in emitted JS/CSS/HTML is rewritten. Dev mode
 * serves the original files untouched.
 */
export function webpAssets(options: WebpAssetsOptions = {}): Plugin {
  const {maxDimension = 2560, quality = 85, minBytes = 16 * 1024} = options

  return {
    name: 'peaks:webp-assets',
    apply: 'build',
    enforce: 'post',
    async generateBundle(_output, bundle) {
      const renames = new Map<string, string>()
      let before = 0
      let after = 0

      const candidates = Object.values(bundle).filter(
        (item) => item.type === 'asset'
          && item.fileName.endsWith('.png')
          && typeof item.source !== 'string'
          && item.source.byteLength >= minBytes,
      )

      const convert = async (fileName: string, source: Uint8Array) => {
        const webp = await sharp(source)
          .resize({
            width: maxDimension,
            height: maxDimension,
            fit: 'inside',
            withoutEnlargement: true,
          })
          .webp({quality, alphaQuality: 100, smartSubsample: true, effort: 5})
          .toBuffer()
        // Keep the PNG when WebP is not a clear win (tiny flat icons).
        if (webp.byteLength >= source.byteLength * 0.9) return
        const webpName = fileName.replace(/\.png$/, '.webp')
        delete bundle[fileName]
        this.emitFile({type: 'asset', fileName: webpName, source: webp})
        renames.set(path.posix.basename(fileName), path.posix.basename(webpName))
        before += source.byteLength
        after += webp.byteLength
      }

      const concurrency = 8
      for (let index = 0; index < candidates.length; index += concurrency) {
        await Promise.all(
          candidates.slice(index, index + concurrency).map((asset) => {
            if (asset.type !== 'asset' || typeof asset.source === 'string') return undefined
            return convert(asset.fileName, asset.source)
          }),
        )
      }

      if (renames.size === 0) return
      // Hashed asset basenames are unique, so a plain substring swap is exact.
      const rewrite = (text: string) => {
        let result = text
        for (const [from, to] of renames) result = result.replaceAll(from, to)
        return result
      }
      for (const item of Object.values(bundle)) {
        if (item.type === 'chunk') {
          item.code = rewrite(item.code)
        } else if (/\.(css|html|js)$/.test(item.fileName)) {
          const text = typeof item.source === 'string'
            ? item.source
            : Buffer.from(item.source).toString('utf8')
          item.source = rewrite(text)
        }
      }

      const mb = (bytes: number) => (bytes / 1048576).toFixed(1)
      this.info(
        `converted ${renames.size} PNG assets to WebP: ${mb(before)} MB -> ${mb(after)} MB`,
      )
    },
  }
}
