import type {EventEmitter} from 'node:events'

/** A desktop app can outlive the launcher that was reading its console pipes. */
export function protectStdio(
  outputs: Pick<EventEmitter, 'on' | 'off'>[] = [process.stdout, process.stderr],
) {
  const onError = (error: NodeJS.ErrnoException) => {
    // Electron logs rejected IPC calls before replying to the renderer. A
    // disconnected launcher's output must not turn that ordinary rejection
    // into a main-process exception. Do not suppress other I/O failures, or
    // touch the backend's request/response streams.
    if (error.code !== 'EPIPE') throw error
  }
  for (const output of outputs) output.on('error', onError)
  return () => {
    for (const output of outputs) output.off('error', onError)
  }
}
