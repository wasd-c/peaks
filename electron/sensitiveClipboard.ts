export interface TextClipboard {
  writeText(value: string): void
  readText(): string
  clear(): void
}

/** Track only the value Peaks copied, including cleanup during app shutdown. */
export function createSensitiveClipboard(clipboard: TextClipboard) {
  let copiedValue: string | undefined
  let timer: ReturnType<typeof setTimeout> | undefined
  let disposed = false

  function clear() {
    if (timer !== undefined) clearTimeout(timer)
    timer = undefined
    const value = copiedValue
    copiedValue = undefined
    if (value === undefined) return
    try {
      if (clipboard.readText() === value) clipboard.clear()
    } catch {
      // An unavailable OS clipboard must not prevent application shutdown.
    }
  }

  function copy(value: string, clearAfterMs = 15_000) {
    if (disposed) return
    // Keep any previous cleanup scheduled if the new clipboard write fails.
    clipboard.writeText(value)
    if (timer !== undefined) clearTimeout(timer)
    copiedValue = value
    const delay = Number.isFinite(clearAfterMs) && clearAfterMs > 0 ? clearAfterMs : 15_000
    timer = setTimeout(clear, delay)
  }

  function dispose() {
    disposed = true
    clear()
  }

  return {copy, clear, dispose}
}
