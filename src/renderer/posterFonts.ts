const fontAssets = import.meta.glob<string>(['./assets/fonts/*.ttf', './assets/fonts/*-OFL.txt'], {
  eager: true,
  import: 'default',
  query: '?url',
})

export interface PosterFonts {
  display: string
  mono: string
}

const families: PosterFonts = {
  display: '"Peaks Poster Display", "Arial Narrow", sans-serif',
  mono: '"Peaks Poster Mono", monospace',
}

const fallbackFamilies: PosterFonts = {
  display: '"Arial Narrow", sans-serif',
  mono: 'monospace',
}

const faces = [
  {file: 'BarlowCondensed-ExtraBold.ttf', family: 'Peaks Poster Display', weight: '800'},
  {file: 'IBMPlexMono-Regular.ttf', family: 'Peaks Poster Mono', weight: '400'},
  {file: 'IBMPlexMono-SemiBold.ttf', family: 'Peaks Poster Mono', weight: '600'},
] as const

let loading: Promise<PosterFonts> | undefined

/** Await before measuring or drawing canvas text. All font URLs are bundled locally. */
export async function loadPosterFonts(): Promise<PosterFonts> {
  if (typeof document === 'undefined' || typeof FontFace === 'undefined' || typeof document.fonts?.add !== 'function') {
    return fallbackFamilies
  }

  if (!loading) {
    loading = Promise.all(faces.map(async ({file, family, weight}) => {
      const url = fontAssets[`./assets/fonts/${file}`]
      if (!url) throw new Error(`Missing poster font: ${file}`)
      return new FontFace(family, `url("${url}")`, {style: 'normal', weight}).load()
    })).then(loaded => {
      for (const face of loaded) document.fonts.add(face)
      return families
    }).catch(() => {
      // Keep exporting if a font cannot load; a later export can retry.
      loading = undefined
      return fallbackFamilies
    })
  }

  return loading
}
