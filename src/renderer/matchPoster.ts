import {gameArtwork, valorantAgentName, valorantAgentPortraitAsset, valorantMapName} from './assets'
import type {MatchShareSummary} from './matchShare'
import {loadPosterFonts} from './posterFonts'
import {displayText, t} from './i18n'

const brandMarks = import.meta.glob<string>('./assets/peaks-mark.png', {
  eager: true,
  import: 'default',
  query: '?url',
})

function loadImage(url?: string): Promise<HTMLImageElement | null> {
  if (!url) return Promise.resolve(null)
  return new Promise(resolve => {
    const image = new Image()
    image.onload = () => resolve(image)
    image.onerror = () => resolve(null)
    image.src = url
  })
}

function drawCover(context: CanvasRenderingContext2D, image: HTMLImageElement, width: number, height: number) {
  const scale = Math.max(width / image.naturalWidth, height / image.naturalHeight)
  const drawnWidth = image.naturalWidth * scale
  const drawnHeight = image.naturalHeight * scale
  context.drawImage(image, (width - drawnWidth) / 2, (height - drawnHeight) / 2, drawnWidth, drawnHeight)
}

/** Trim transparent source padding so every official standing portrait fills its allotted height. */
function portraitBounds(image: HTMLImageElement) {
  const canvas = document.createElement('canvas')
  canvas.width = image.naturalWidth
  canvas.height = image.naturalHeight
  const context = canvas.getContext('2d', {willReadFrequently: true})
  const full = {x: 0, y: 0, width: canvas.width, height: canvas.height}
  if (!context) return full
  try {
    context.drawImage(image, 0, 0)
    const pixels = context.getImageData(0, 0, canvas.width, canvas.height).data
    let left = canvas.width, top = canvas.height, right = -1, bottom = -1
    for (let y = 0; y < canvas.height; y++) {
      for (let x = 0; x < canvas.width; x++) {
        if (pixels[(y * canvas.width + x) * 4 + 3] < 16) continue
        left = Math.min(left, x)
        top = Math.min(top, y)
        right = Math.max(right, x)
        bottom = Math.max(bottom, y)
      }
    }
    return right < left ? full : {x: left, y: top, width: right - left + 1, height: bottom - top + 1}
  } catch {
    return full
  }
}

function fittedText(context: CanvasRenderingContext2D, text: string, x: number, y: number, maxWidth: number) {
  if (context.measureText(text).width <= maxWidth) {
    context.fillText(text, x, y)
    return
  }
  const characters = Array.from(text)
  while (characters.length > 1 && context.measureText(`${characters.join('')}…`).width > maxWidth) characters.pop()
  context.fillText(`${characters.join('').trimEnd()}…`, x, y)
}

export function matchPosterResult(result: string): string {
  if (/^(win|victory)$/i.test(result)) return t('VICTORY')
  if (/^(loss|defeat)$/i.test(result)) return t('DEFEAT')
  return displayText(result).toLocaleUpperCase()
}

/** A small, stable texture avoids flat gradients without changing between exports. */
function filmGrain(context: CanvasRenderingContext2D, width: number, height: number, color: string) {
  let seed = 7189
  const random = () => ((seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0) / 4294967296)
  context.save()
  context.fillStyle = color
  for (let index = 0; index < 12000; index++) {
    context.globalAlpha = 0.015 + random() * 0.045
    context.fillRect(random() * width, random() * height, 0.6 + random() * 1.4, 0.6 + random())
  }
  context.restore()
}

/** Export-space coordinates are fixed print geometry; palette values come from theme tokens. */
export async function renderMatchPoster(summary: MatchShareSummary): Promise<Blob> {
  const width = 1600
  const height = 900
  const canvas = document.createElement('canvas')
  canvas.width = width
  canvas.height = height
  const context = canvas.getContext('2d')
  if (!context) throw new Error('Your device could not create the match image.')

  // Resolve custom properties in the app's theme before handing colors to canvas.
  const themeElement = document.querySelector('.peaks-app') ?? document.documentElement
  canvas.style.display = 'none'
  canvas.style.colorScheme = 'dark'
  themeElement.appendChild(canvas)
  const color = (token: string) => {
    canvas.style.color = `var(${token})`
    return getComputedStyle(canvas).color
  }
  const background = color('--color-background-body')
  const foreground = color('--color-on-dark')
  const secondary = color('--color-text-secondary')
  const light = color('--peaks-poster-light')
  const resultColor = color(/^(win|victory)$/i.test(summary.result)
    ? '--color-success' : /^(loss|defeat)$/i.test(summary.result) ? '--color-error' : '--color-on-dark')
  canvas.remove()
  const map = summary.game === 'VALORANT' ? valorantMapName(summary.map) : summary.map ?? summary.game
  const character = summary.game === 'VALORANT' ? valorantAgentName(summary.character) : summary.character
  const [artwork, portrait, mark, fonts] = await Promise.all([
    loadImage(gameArtwork(summary.game, summary.map)),
    loadImage(summary.game === 'VALORANT' ? valorantAgentPortraitAsset(summary.character) : undefined),
    loadImage(brandMarks['./assets/peaks-mark.png']),
    loadPosterFonts(),
  ])

  context.fillStyle = background
  context.fillRect(0, 0, width, height)
  if (artwork) {
    context.save()
    context.globalAlpha = 0.28
    drawCover(context, artwork, width, height)
    context.restore()
  }
  const darkness = context.createLinearGradient(0, 0, width, 0)
  darkness.addColorStop(0, background)
  darkness.addColorStop(0.35, background)
  darkness.addColorStop(0.94, 'transparent')
  context.fillStyle = darkness
  context.fillRect(0, 0, width, height)

  // An ascending slash is the Peaks signature. The map and light share its geometry.
  context.save()
  context.beginPath()
  context.moveTo(717, height)
  context.lineTo(1048, 0)
  context.lineTo(1400, 0)
  context.lineTo(1069, height)
  context.closePath()
  context.clip()
  if (artwork) {
    context.globalAlpha = 0.56
    drawCover(context, artwork, width, height)
    context.globalAlpha = 1
  }
  const beam = context.createLinearGradient(0, 0, 0, height)
  beam.addColorStop(0, 'transparent')
  beam.addColorStop(0.55, light)
  beam.addColorStop(1, 'transparent')
  context.globalAlpha = 0.36
  context.fillStyle = beam
  context.fillRect(0, 0, width, height)
  context.restore()

  context.save()
  context.strokeStyle = foreground
  context.globalAlpha = 0.24
  context.lineWidth = 1
  context.beginPath()
  context.moveTo(1048, 0)
  context.lineTo(717, height)
  context.moveTo(1422, 0)
  context.lineTo(1091, height)
  context.stroke()
  context.restore()

  // Oversized outline lettering belongs to the scenery; the readable map is in the header.
  if (map) {
    context.save()
    context.translate(1538, 767)
    context.rotate(-Math.PI / 2)
    context.strokeStyle = foreground
    context.globalAlpha = 0.14
    context.lineWidth = 1.5
    context.font = `800 200px ${fonts.display}`
    context.strokeText(map.toLocaleUpperCase(), 0, 0, 670)
    context.restore()
  }
  filmGrain(context, width, height, foreground)

  if (portrait) {
    const bounds = portraitBounds(portrait)
    const scale = Math.min(728 / bounds.height, 700 / bounds.width)
    const portraitWidth = bounds.width * scale
    const portraitHeight = bounds.height * scale
    context.save()
    context.shadowColor = background
    context.shadowBlur = 32
    context.shadowOffsetX = -12
    context.drawImage(portrait, bounds.x, bounds.y, bounds.width, bounds.height,
      1168 - portraitWidth / 2, 835 - portraitHeight, portraitWidth, portraitHeight)
    context.restore()
  }

  // A narrow footer fade grounds the figure without cropping their standing artwork.
  const floor = context.createLinearGradient(0, 805, 0, height)
  floor.addColorStop(0, 'transparent')
  floor.addColorStop(1, background)
  context.fillStyle = floor
  context.fillRect(0, 805, width, 95)
  context.textBaseline = 'alphabetic'
  context.textAlign = 'left'
  context.fillStyle = foreground
  context.font = `600 22px ${fonts.mono}`
  context.letterSpacing = '1px'
  fittedText(context, [displayText(summary.mode), map].filter(Boolean).join(' / ').toLocaleUpperCase(), 76, 81, 1120)
  context.letterSpacing = '0px'
  if (mark) context.drawImage(mark, 1350, 46, 40, 40)
  context.font = `800 38px ${fonts.display}`
  context.letterSpacing = '2px'
  context.fillText('PEAKS', 1404, 79)
  context.letterSpacing = '0px'

  const result = matchPosterResult(summary.result)
  let resultSize = 192
  context.font = `800 ${resultSize}px ${fonts.display}`
  while (resultSize > 65 && context.measureText(result).width > 785) {
    context.font = `800 ${--resultSize}px ${fonts.display}`
  }
  fittedText(context, result, 68, 280, 785)
  context.fillStyle = resultColor
  context.fillRect(78, 312, 48, 5)
  context.fillStyle = foreground
  context.font = `800 88px ${fonts.display}`
  fittedText(context, summary.score.replace(/\s*[:–]\s*/g, ' — '), 74, 394, 480)
  context.font = `400 15px ${fonts.mono}`
  context.fillStyle = secondary
  context.fillText(t('FINAL SCORE'), 80, 423)

  context.fillStyle = foreground
  if (summary.playerName) {
    context.font = `600 27px ${fonts.mono}`
    fittedText(context, summary.playerName, 78, 495, 700)
  }
  if (summary.kda) {
    context.font = `800 116px ${fonts.display}`
    fittedText(context, summary.kda, 72, 614, 710)
    context.font = `400 16px ${fonts.mono}`
    context.fillStyle = secondary
    context.fillText(summary.kda.split('/').length === 3 ? t('KILLS / DEATHS / ASSISTS') : t('PERFORMANCE'), 80, 649)
  }

  const metrics = [
    {label: 'AVG. COMBAT SCORE', value: summary.combatScore},
    {label: 'DAMAGE / ROUND', value: summary.damagePerRound},
  ].filter(metric => metric.value != null)
  metrics.forEach((metric, index) => {
    const x = 78 + index * 266
    context.fillStyle = foreground
    context.font = `800 52px ${fonts.display}`
    fittedText(context, metric.value!, x, 733, 220)
    context.fillStyle = secondary
    context.font = `400 17px ${fonts.mono}`
    fittedText(context, t(metric.label), x + 1, 758, 250)
  })

  // Match-earned tags are black with white type; history tags use the inverse.
  // Wrap into two reserved rows, keeping tags clear of all stats and the agent.
  let tagX = 78
  let tagY = 794
  for (const tag of summary.tags.slice(0, 4)) {
    context.font = `600 21px ${fonts.mono}`
    const tagWidth = Math.min(context.measureText(tag.label).width + 32, 343)
    if (tagX + tagWidth > 784) {
      tagX = 78
      tagY += 43
    }
    if (tagY > 837) break
    context.fillStyle = tag.source === 'match' ? background : foreground
    context.fillRect(tagX, tagY, tagWidth, 36)
    context.strokeStyle = foreground
    context.lineWidth = 1
    context.strokeRect(tagX, tagY, tagWidth, 36)
    context.fillStyle = tag.source === 'match' ? foreground : background
    fittedText(context, tag.label, tagX + 16, tagY + 25, tagWidth - 32)
    tagX += tagWidth + 12
  }

  if (character) {
    context.fillStyle = foreground
    context.textAlign = 'right'
    context.font = `800 39px ${fonts.display}`
    context.letterSpacing = '3px'
    fittedText(context, character.toLocaleUpperCase(), 1518, 859, 620)
    context.letterSpacing = '0px'
    context.textAlign = 'left'
  }

  return new Promise((resolve, reject) => canvas.toBlob(
    blob => blob ? resolve(blob) : reject(new Error('The PNG could not be exported. Please try again.')),
    'image/png',
  ))
}
