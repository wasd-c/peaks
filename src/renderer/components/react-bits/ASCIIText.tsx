import {Fragment, useEffect, useRef, useState} from 'react'
import * as THREE from 'three'
import './ASCIIText.css'

const ASCII_CHARSET = ' .\'`^",:;Il!i~+_-?][}{1)(|/tfjrxnuvczXYUJCLQ0OZmwqpdbkhao*#MW&8%B@$'
const FONT_FAMILY = '"Cascadia Mono", "SF Mono", Consolas, "Liberation Mono", "Courier New", monospace'

const vertexShader = `
varying vec2 vUv;
uniform float uTime;
uniform float uEnableWaves;

void main() {
  vUv = uv;
  float time = uTime * 5.0;
  float waveFactor = uEnableWaves;
  vec3 transformed = position;

  transformed.x += sin(time + position.y) * 0.5 * waveFactor;
  transformed.y += cos(time + position.z) * 0.15 * waveFactor;
  transformed.z += sin(time + position.x) * waveFactor;

  gl_Position = projectionMatrix * modelViewMatrix * vec4(transformed, 1.0);
}
`

const fragmentShader = `
varying vec2 vUv;
uniform float uTime;
uniform sampler2D uTexture;

void main() {
  float time = uTime;
  vec2 pos = vUv;
  float r = texture2D(uTexture, pos + cos(time + pos.x) * 0.01).r;
  float g = texture2D(uTexture, pos + tan(time * 0.5 + pos.x - time) * 0.01).g;
  float b = texture2D(uTexture, pos - cos(time * 2.0 + time + pos.y) * 0.01).b;
  float a = texture2D(uTexture, pos).a;
  gl_FragColor = vec4(r, g, b, a);
}
`

const mapRange = (value: number, inStart: number, inEnd: number, outStart: number, outEnd: number) =>
  ((value - inStart) / Math.max(inEnd - inStart, Number.EPSILON)) * (outEnd - outStart) + outStart

export interface ASCIITextInlineImage {
  src: string
  token: string
  heightRatio?: number
}

interface InlineImageSize {
  height: number
  width: number
}

const loadInlineImage = (src: string) =>
  new Promise<HTMLImageElement>((resolve, reject) => {
    const image = new Image()
    image.decoding = 'async'
    image.onload = () => resolve(image)
    image.onerror = () => reject(new Error('Inline ASCII artwork could not be loaded'))
    image.src = src
  })

class TextCanvas {
  readonly canvas: HTMLCanvasElement
  readonly context: CanvasRenderingContext2D
  readonly text: string
  readonly lines: string[]
  readonly fontSize: number
  readonly color: string
  readonly inlineImage?: ASCIITextInlineImage
  private loadedInlineImage: HTMLImageElement | null = null

  constructor(
    text: string,
    fontSize: number,
    color: string,
    maxCharactersPerLine?: number,
    inlineImage?: ASCIITextInlineImage,
  ) {
    this.canvas = document.createElement('canvas')
    const context = this.canvas.getContext('2d')
    if (!context) throw new Error('Canvas text rendering is unavailable')
    this.context = context
    this.text = text
    this.lines = wrapText(text, maxCharactersPerLine)
    this.fontSize = fontSize
    this.color = color
    this.inlineImage = inlineImage
  }

  get font() {
    return `600 ${this.fontSize}px ${FONT_FAMILY}`
  }

  async prepare() {
    if (!this.inlineImage?.src || !this.inlineImage.token) return
    try {
      this.loadedInlineImage = await loadInlineImage(this.inlineImage.src)
    } catch {
      // The sentence still renders without the decorative inline artwork.
      this.loadedInlineImage = null
    }
  }

  resize() {
    this.context.font = this.font
    const metrics = this.lines.map(line => this.context.measureText(this.textOnly(line)))
    const ascent = Math.max(...metrics.map(value => value.actualBoundingBoxAscent || this.fontSize))
    const descent = Math.max(...metrics.map(value => value.actualBoundingBoxDescent || this.fontSize * 0.25))
    const lineHeight = this.fontSize * 1.15
    this.canvas.width = Math.ceil(Math.max(...this.lines.map(line => this.measureLine(line)))) + 20
    this.canvas.height = Math.ceil(ascent + descent + lineHeight * (this.lines.length - 1)) + 20
  }

  render() {
    this.context.clearRect(0, 0, this.canvas.width, this.canvas.height)
    this.context.fillStyle = this.color
    this.context.font = this.font
    const metrics = this.lines.map(line => this.context.measureText(this.textOnly(line)))
    const ascent = Math.max(...metrics.map(value => value.actualBoundingBoxAscent || this.fontSize))
    const lineHeight = this.fontSize * 1.15
    this.lines.forEach((line, index) => {
      const lineWidth = this.measureLine(line)
      const baseline = 10 + ascent + lineHeight * index
      this.drawLine(line, (this.canvas.width - lineWidth) / 2, baseline)
    })
  }

  private textOnly(line: string) {
    return this.inlineImage?.token ? line.split(this.inlineImage.token).join('') : line
  }

  private imageSize(): InlineImageSize | null {
    const image = this.loadedInlineImage
    if (!image?.naturalWidth || !image.naturalHeight) return null
    const height = this.fontSize * (this.inlineImage?.heightRatio ?? 0.86)
    return {height, width: height * (image.naturalWidth / image.naturalHeight)}
  }

  private measureLine(line: string) {
    const token = this.inlineImage?.token
    if (!token) return this.context.measureText(line).width
    const segments = line.split(token)
    const image = this.imageSize()
    return segments.reduce(
      (width, segment, index) =>
        width
        + this.context.measureText(segment).width
        + (index < segments.length - 1 ? image?.width ?? 0 : 0),
      0,
    )
  }

  private drawLine(line: string, startX: number, baseline: number) {
    const token = this.inlineImage?.token
    const image = this.loadedInlineImage
    const imageSize = this.imageSize()
    if (!token || !image || !imageSize) {
      this.context.fillText(this.textOnly(line), startX, baseline)
      return
    }

    const segments = line.split(token)
    let cursorX = startX
    segments.forEach((segment, index) => {
      this.context.fillText(segment, cursorX, baseline)
      cursorX += this.context.measureText(segment).width
      if (index >= segments.length - 1) return
      this.context.drawImage(
        image,
        cursorX,
        baseline - imageSize.height * 0.86,
        imageSize.width,
        imageSize.height,
      )
      cursorX += imageSize.width
    })
  }
}

const wrapText = (text: string, maxCharactersPerLine?: number): string[] => {
  if (!maxCharactersPerLine || text.length <= maxCharactersPerLine) return [text]
  const lines: string[] = []
  let current = ''
  for (const word of text.split(/\s+/)) {
    const candidate = current ? `${current} ${word}` : word
    if (candidate.length > maxCharactersPerLine && current) {
      lines.push(current)
      current = word
    } else {
      current = candidate
    }
  }
  if (current) lines.push(current)
  return lines.length ? lines : [text]
}

class AsciiFilter {
  readonly domElement = document.createElement('div')
  readonly output = document.createElement('pre')
  readonly sampler = document.createElement('canvas')
  readonly context: CanvasRenderingContext2D
  private readonly renderer: THREE.WebGLRenderer
  private readonly fontSize: number
  private width = 1
  private height = 1
  private center = {x: 0.5, y: 0.5}
  private pointer = {x: 0.5, y: 0.5}
  private hue = 0

  constructor(renderer: THREE.WebGLRenderer, fontSize: number) {
    const context = this.sampler.getContext('2d', {willReadFrequently: true})
    if (!context) throw new Error('ASCII sampling is unavailable')
    this.context = context
    this.renderer = renderer
    this.fontSize = Math.max(2, fontSize)
    this.domElement.className = 'ascii-text-filter'
    this.output.className = 'ascii-text-output'
    this.sampler.className = 'ascii-text-sampler'
    this.domElement.append(this.output, this.sampler)
    this.context.imageSmoothingEnabled = false
  }

  setSize(width: number, height: number) {
    this.width = Math.max(width, 1)
    this.height = Math.max(height, 1)
    this.renderer.setSize(this.width, this.height, false)

    this.context.font = `${this.fontSize}px ${FONT_FAMILY}`
    const characterWidth = Math.max(this.context.measureText('A').width, 1)
    const columns = Math.max(1, Math.floor(this.width / characterWidth))
    const rows = Math.max(1, Math.floor(this.height / this.fontSize))
    this.sampler.width = columns
    this.sampler.height = rows
    this.center = {x: this.width / 2, y: this.height / 2}
    this.pointer = {...this.center}
    this.output.style.fontFamily = FONT_FAMILY
    this.output.style.fontSize = `${this.fontSize}px`
  }

  setPointer(x: number, y: number) {
    this.pointer = {x, y}
  }

  render(scene: THREE.Scene, camera: THREE.Camera, allowHueMotion: boolean) {
    this.renderer.render(scene, camera)
    const width = this.sampler.width
    const height = this.sampler.height
    if (!width || !height) return

    this.context.clearRect(0, 0, width, height)
    this.context.drawImage(this.renderer.domElement, 0, 0, width, height)
    const pixels = this.context.getImageData(0, 0, width, height).data
    let output = ''

    for (let y = 0; y < height; y += 1) {
      for (let x = 0; x < width; x += 1) {
        const offset = (x + y * width) * 4
        const alpha = pixels[offset + 3]
        if (alpha === 0) {
          output += ' '
          continue
        }
        const luminance = (0.3 * pixels[offset] + 0.6 * pixels[offset + 1] + 0.1 * pixels[offset + 2]) / 255
        const index = Math.max(0, Math.min(ASCII_CHARSET.length - 1, Math.floor(luminance * (ASCII_CHARSET.length - 1))))
        output += ASCII_CHARSET[index]
      }
      output += '\n'
    }

    this.output.textContent = output
    if (allowHueMotion) {
      const degrees = (Math.atan2(this.pointer.y - this.center.y, this.pointer.x - this.center.x) * 180) / Math.PI
      this.hue += (degrees - this.hue) * 0.075
      this.domElement.style.filter = `hue-rotate(${this.hue.toFixed(1)}deg)`
    }
  }
}

interface AsciiSceneOptions {
  text: string
  asciiFontSize: number
  textFontSize: number
  textColor: string
  maxCharactersPerLine?: number
  planeBaseHeight: number
  enableWaves: boolean
  paused: boolean
  fps: number
  inlineImage?: ASCIITextInlineImage
}

class AsciiScene {
  private readonly container: HTMLElement
  private readonly options: AsciiSceneOptions
  private readonly camera: THREE.PerspectiveCamera
  private readonly scene = new THREE.Scene()
  private readonly textCanvas: TextCanvas
  private geometry: THREE.PlaneGeometry | null = null
  private material: THREE.ShaderMaterial | null = null
  private texture: THREE.CanvasTexture | null = null
  private mesh: THREE.Mesh | null = null
  private renderer: THREE.WebGLRenderer | null = null
  private filter: AsciiFilter | null = null
  private animationFrame: number | null = null
  private lastFrame = 0
  private disposed = false
  private width = 1
  private height = 1
  private pointer = {x: 0.5, y: 0.5}

  constructor(options: AsciiSceneOptions, container: HTMLElement, width: number, height: number) {
    this.options = options
    this.container = container
    this.width = Math.max(width, 1)
    this.height = Math.max(height, 1)
    this.camera = new THREE.PerspectiveCamera(45, this.width / this.height, 1, 1000)
    this.camera.position.z = 30
    this.textCanvas = new TextCanvas(
      options.text,
      options.textFontSize,
      options.textColor,
      options.maxCharactersPerLine,
      options.inlineImage,
    )
  }

  async init() {
    try {
      await document.fonts?.ready
    } catch {
      // Local system font fallbacks keep the scene usable without a network.
    }
    if (this.disposed) return

    await this.textCanvas.prepare()
    if (this.disposed) return

    this.textCanvas.resize()
    this.textCanvas.render()
    this.texture = new THREE.CanvasTexture(this.textCanvas.canvas)
    this.texture.minFilter = THREE.NearestFilter

    const textAspect = this.textCanvas.canvas.width / Math.max(this.textCanvas.canvas.height, 1)
    const planeHeight = this.options.planeBaseHeight
    this.geometry = new THREE.PlaneGeometry(planeHeight * textAspect, planeHeight, 36, 36)
    this.material = new THREE.ShaderMaterial({
      vertexShader,
      fragmentShader,
      transparent: true,
      uniforms: {
        uTime: {value: 0},
        uTexture: {value: this.texture},
        uEnableWaves: {value: this.options.enableWaves ? 1 : 0},
      },
    })
    this.mesh = new THREE.Mesh(this.geometry, this.material)
    this.scene.add(this.mesh)

    this.renderer = new THREE.WebGLRenderer({antialias: false, alpha: true, powerPreference: 'low-power'})
    this.renderer.setPixelRatio(1)
    this.renderer.setClearColor(0x000000, 0)
    this.filter = new AsciiFilter(this.renderer, this.options.asciiFontSize)
    this.container.appendChild(this.filter.domElement)
    this.setSize(this.width, this.height)
    this.container.addEventListener('pointermove', this.onPointerMove, {passive: true})
    this.container.addEventListener('pointerleave', this.onPointerLeave)
  }

  setSize(width: number, height: number) {
    this.width = Math.max(width, 1)
    this.height = Math.max(height, 1)
    this.pointer = {x: this.width / 2, y: this.height / 2}
    this.camera.aspect = this.width / this.height
    this.camera.updateProjectionMatrix()
    this.filter?.setSize(this.width, this.height)
    this.filter?.setPointer(this.pointer.x, this.pointer.y)
  }

  start() {
    if (this.options.paused) {
      this.render(0)
      return
    }
    const animate = (now: number) => {
      this.animationFrame = requestAnimationFrame(animate)
      const interval = 1000 / Math.max(this.options.fps, 1)
      if (now - this.lastFrame < interval) return
      this.lastFrame = now - ((now - this.lastFrame) % interval)
      this.render(now / 1000)
    }
    this.animationFrame = requestAnimationFrame(animate)
  }

  dispose() {
    this.disposed = true
    if (this.animationFrame !== null) cancelAnimationFrame(this.animationFrame)
    this.container.removeEventListener('pointermove', this.onPointerMove)
    this.container.removeEventListener('pointerleave', this.onPointerLeave)
    this.filter?.domElement.remove()
    this.scene.clear()
    this.geometry?.dispose()
    this.material?.dispose()
    this.texture?.dispose()
    this.renderer?.dispose()
    this.renderer?.forceContextLoss()
  }

  private readonly onPointerMove = (event: PointerEvent) => {
    const bounds = this.container.getBoundingClientRect()
    this.pointer = {
      x: event.clientX - bounds.left,
      y: event.clientY - bounds.top,
    }
    this.filter?.setPointer(this.pointer.x, this.pointer.y)
  }

  private readonly onPointerLeave = () => {
    this.pointer = {x: this.width / 2, y: this.height / 2}
    this.filter?.setPointer(this.pointer.x, this.pointer.y)
  }

  private render(time: number) {
    if (!this.mesh || !this.material || !this.texture || !this.filter) return
    this.textCanvas.render()
    this.texture.needsUpdate = true
    this.material.uniforms.uTime.value = Math.sin(time)
    if (!this.options.paused) {
      const targetX = mapRange(this.pointer.y, 0, this.height, 0.5, -0.5)
      const targetY = mapRange(this.pointer.x, 0, this.width, -0.5, 0.5)
      this.mesh.rotation.x += (targetX - this.mesh.rotation.x) * 0.05
      this.mesh.rotation.y += (targetY - this.mesh.rotation.y) * 0.05
    }
    this.filter.render(this.scene, this.camera, !this.options.paused)
  }
}

export interface ASCIITextProps {
  text?: string
  enableWaves?: boolean
  asciiFontSize?: number
  textFontSize?: number
  planeBaseHeight?: number
  textColor?: string
  maxCharactersPerLine?: number
  paused?: boolean
  fps?: number
  className?: string
  inlineImage?: ASCIITextInlineImage
}

export default function ASCIIText({
  text = 'Hello World!',
  enableWaves = true,
  asciiFontSize = 12,
  textFontSize = 200,
  planeBaseHeight = 8,
  textColor = '#fdf9f3',
  maxCharactersPerLine,
  paused = false,
  fps = 30,
  className,
  inlineImage,
}: ASCIITextProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const sceneRef = useRef<AsciiScene | null>(null)
  const [ready, setReady] = useState(false)

  useEffect(() => {
    const container = containerRef.current
    if (!container) return
    let cancelled = false
    let resizeObserver: ResizeObserver | null = null

    const setup = async () => {
      const bounds = container.getBoundingClientRect()
      if (bounds.width <= 0 || bounds.height <= 0) return
      const scene = new AsciiScene(
        {
          text,
          enableWaves,
          asciiFontSize,
          textFontSize,
          planeBaseHeight,
          textColor,
          maxCharactersPerLine,
          paused,
          fps,
          inlineImage,
        },
        container,
        bounds.width,
        bounds.height,
      )

      try {
        await scene.init()
        if (cancelled) {
          scene.dispose()
          return
        }
        sceneRef.current = scene
        scene.start()
        setReady(true)
        resizeObserver = new ResizeObserver(entries => {
          const next = entries[0]?.contentRect
          if (next && next.width > 0 && next.height > 0) scene.setSize(next.width, next.height)
        })
        resizeObserver.observe(container)
      } catch {
        scene.dispose()
        // A visible local-font fallback remains when Canvas or WebGL is unavailable.
      }
    }

    void setup()
    return () => {
      cancelled = true
      resizeObserver?.disconnect()
      sceneRef.current?.dispose()
      sceneRef.current = null
    }
  }, [
    asciiFontSize,
    enableWaves,
    fps,
    inlineImage,
    maxCharactersPerLine,
    paused,
    planeBaseHeight,
    text,
    textColor,
    textFontSize,
  ])

  const fallbackSegments = inlineImage?.token ? text.split(inlineImage.token) : [text]

  return (
    <div
      ref={containerRef}
      className={`ascii-text-container${className ? ` ${className}` : ''}`}
      data-ready={ready || undefined}
      aria-hidden="true">
      <span className="ascii-text-fallback">
        <span className="ascii-text-fallback__content">
          {fallbackSegments.map((segment, index) => (
            <Fragment key={`${index}-${segment}`}>
              {segment}
              {inlineImage && index < fallbackSegments.length - 1 ? (
                <img
                  alt=""
                  aria-hidden="true"
                  className="ascii-text-fallback__inline-image"
                  src={inlineImage.src}
                />
              ) : null}
            </Fragment>
          ))}
        </span>
      </span>
    </div>
  )
}
