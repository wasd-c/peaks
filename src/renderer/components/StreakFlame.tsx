import {useEffect, useRef} from 'react'
import {HStack} from '@astryxdesign/core/HStack'
import {Icon} from '@astryxdesign/core/Icon'
import {Flame} from 'lucide-react'
import {Color, Mesh, Program, Renderer, Triangle} from 'ogl'

const vertex = `
attribute vec2 position;
attribute vec2 uv;
varying vec2 vUv;
void main() { vUv = uv; gl_Position = vec4(position, 0.0, 1.0); }
`
const fragment = `
precision highp float;
varying vec2 vUv;
uniform float time;
uniform vec3 fire;
uniform vec3 ember;
uniform vec3 core;
float hash(vec2 p) { return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
float noise(vec2 p) {
  vec2 i = floor(p), f = fract(p);
  f = f * f * (3.0 - 2.0 * f);
  return mix(mix(hash(i), hash(i + vec2(1,0)), f.x), mix(hash(i + vec2(0,1)), hash(i + vec2(1,1)), f.x), f.y);
}
float turbulence(vec2 p) {
  float n = 0.0, amplitude = 0.5;
  for (int i = 0; i < 4; i++) { n += amplitude * noise(p); p = p * 2.03 + 7.1; amplitude *= 0.5; }
  return n;
}
void main() {
  vec2 p = vec2((vUv.x - 0.5) * 2.0, vUv.y);
  float y = p.y;
  // Upward advection wrinkles the boundary and breaks the tips into tongues.
  float n = turbulence(vec2(p.x * 3.8, y * 4.2 - time * 1.6));
  float curl = turbulence(vec2(p.x * 2.0 + 2.1, y * 3.0 - time * 0.9)) - 0.5;
  float x = p.x + curl * y * 0.55;
  float envelope = 1.0 - pow(abs(x) / 0.68, 1.5) - y * 1.18;
  float heat = envelope + (n - 0.5) * (0.3 + y * 0.85);
  float flame = smoothstep(0.02, 0.22, heat);
  float base = smoothstep(0.01, 0.15, y);
  float edge = 1.0 - smoothstep(0.88, 1.0, y);
  float glow = exp(-9.0 * (p.x * p.x + pow(y - 0.28, 2.0))) * 0.18;
  vec3 color = mix(fire, ember, smoothstep(0.13, 0.6, heat));
  color = mix(color, core, smoothstep(0.55, 0.95, heat) * 0.85);
  float alpha = max(flame * base * edge * 0.92, glow);
  // Three sparse embers rise on independent cycles.
  for (int i = 0; i < 3; i++) {
    float seed = float(i);
    float life = fract(time * (0.28 + seed * 0.035) + seed * 0.37);
    vec2 spark = vec2(sin(seed * 7.0 + life * 3.0) * (0.18 + life * 0.2), 0.35 + life * 0.62);
    float light = (1.0 - smoothstep(0.005, 0.022, length((p - spark) * vec2(1.0, 0.65)))) * sin(life * 3.14159);
    color = mix(color, core, light);
    alpha = max(alpha, light * 0.8);
  }
  gl_FragColor = vec4(color, alpha);
}
`

/** One small GPU surface; sleeps offscreen and freezes for reduced motion. */
export function StreakFlame() {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  useEffect(() => {
    const canvas = canvasRef.current
    const surface = canvas?.parentElement
    if (!canvas || !surface) return
    let renderer: Renderer
    try {
      renderer = new Renderer({canvas, alpha: true, antialias: false, dpr: Math.min(window.devicePixelRatio || 1, 2), powerPreference: 'low-power'})
    } catch { return }
    const gl = renderer.gl
    renderer.setSize(surface.clientWidth, surface.clientHeight)
    const palette = getComputedStyle(canvas)
    const program = new Program(gl, {vertex, fragment, transparent: true, depthTest: false, depthWrite: false,
      uniforms: {time: {value: 3.7}, ...Object.fromEntries(['fire', 'ember', 'core'].map(name => [name, {value: new Color(palette.getPropertyValue(`--color-tft-streak-${name}`).trim())}]))}})
    const geometry = new Triangle(gl)
    const mesh = new Mesh(gl, {geometry, program})
    let frame = 0, visible = false, lastFrame = 0, elapsed = 3.7, lost = false
    const preference = window.matchMedia('(prefers-reduced-motion: reduce)')
    const reduced = () => preference.matches || Boolean(canvas.closest('.reduce-motion, [data-reduce-motion="true"]'))
    const render = () => { renderer.render({scene: mesh}); canvas.dataset.ready = 'true' }
    const draw = (now: number) => {
      frame = 0
      if (!visible || document.hidden || lost) return
      if (now - lastFrame >= 1000 / 30) {
        elapsed += Math.min((now - lastFrame) / 1000, 0.05)
        lastFrame = now
        program.uniforms.time.value = elapsed
        render()
      }
      if (!reduced()) frame = requestAnimationFrame(draw)
    }
    const resume = () => {
      cancelAnimationFrame(frame)
      frame = 0
      lastFrame = performance.now()
      if (visible && !document.hidden && !lost) {
        render()
        if (!reduced()) frame = requestAnimationFrame(draw)
      }
    }
    const resize = new ResizeObserver(() => { renderer.setSize(surface.clientWidth, surface.clientHeight); resume() })
    resize.observe(surface)
    const intersection = new IntersectionObserver(entries => { visible = entries[0].isIntersecting; resume() })
    intersection.observe(canvas)
    const app = canvas.closest('.peaks-app')
    const settings = new MutationObserver(resume)
    if (app) settings.observe(app, {attributes: true, attributeFilter: ['class', 'data-reduce-motion']})
    const onLoss = () => { lost = true; cancelAnimationFrame(frame); delete canvas.dataset.ready }
    canvas.addEventListener('webglcontextlost', onLoss)
    document.addEventListener('visibilitychange', resume)
    preference.addEventListener('change', resume)
    return () => {
      cancelAnimationFrame(frame)
      resize.disconnect(); intersection.disconnect(); settings.disconnect()
      document.removeEventListener('visibilitychange', resume)
      preference.removeEventListener('change', resume)
      canvas.removeEventListener('webglcontextlost', onLoss)
      delete canvas.dataset.ready
      geometry.remove(); program.remove()
      // React StrictMode reuses this canvas for its second effect setup.
      // Free our resources without permanently losing the shared context.
    }
  }, [])
  return <HStack className="pd-tft-streak__effect pd-tft-streak__flame" aria-hidden>
    <canvas ref={canvasRef} className="pd-tft-streak__canvas" />
    <Icon icon={Flame} className="pd-tft-streak__fallback" />
  </HStack>
}
