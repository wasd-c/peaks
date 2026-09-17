import path from 'node:path'

export interface BackendLaunchOptions {
  appPath: string
  environment: NodeJS.ProcessEnv
  isPackaged: boolean
  platform: NodeJS.Platform
  resourcesPath: string
  virtualenvExists: (candidate: string) => boolean
}

export interface BackendLaunch {
  args: string[]
  command: string
  environment: NodeJS.ProcessEnv
}

export interface PendingBackendRequest {
  reject: (error: Error) => void
}

/** Reject and remove every request when a child cannot start or exits. */
export function rejectPendingBackendRequests(
  pending: Map<number, PendingBackendRequest>,
  error: Error,
) {
  for (const request of pending.values()) request.reject(error)
  pending.clear()
}

/** Resolve the exact backend and browser runtime used by Electron. */
export function resolveBackendLaunch(options: BackendLaunchOptions): BackendLaunch {
  const {
    appPath,
    environment,
    isPackaged,
    platform,
    resourcesPath,
    virtualenvExists,
  } = options
  const runtimePath = platform === 'win32' ? path.win32 : path.posix
  const runtimeEnvironment: NodeJS.ProcessEnv = {
    ...environment,
    PEAKS_DEMO: environment.PEAKS_DEMO || '0',
    // Node writes IPC requests as UTF-8. Pin Python's pipe encoding so Riot
    // names and localized map/agent text never depend on the Windows code page.
    PYTHONIOENCODING: 'utf-8',
    PYTHONUTF8: '1',
  }

  if (isPackaged) {
    // A packaged build must never fall back to PATH or a caller-selected
    // interpreter. Both would escape the signed application boundary.
    delete runtimeEnvironment.PEAKS_PYTHON
    delete runtimeEnvironment.PEAKS_PACKAGING_BROWSER_SMOKE
    delete runtimeEnvironment.PYTHONHOME
    delete runtimeEnvironment.PYTHONPATH
    runtimeEnvironment.PLAYWRIGHT_BROWSERS_PATH = runtimePath.join(
      resourcesPath,
      'patchright-browsers',
    )
    return {
      args: [],
      command: runtimePath.join(
        resourcesPath,
        'backend',
        platform === 'win32' ? 'PeaksBridge.exe' : 'PeaksBridge',
      ),
      environment: runtimeEnvironment,
    }
  }

  const virtualenvPython = runtimePath.join(
    appPath,
    '.venv',
    platform === 'win32' ? 'Scripts/python.exe' : 'bin/python',
  )
  const command = environment.PEAKS_PYTHON
    || (virtualenvExists(virtualenvPython)
      ? virtualenvPython
      : platform === 'win32' ? 'python' : 'python3')
  runtimeEnvironment.PYTHONPATH = runtimePath.join(appPath, 'src')
  return {
    args: ['-m', 'peaks.bridge'],
    command,
    environment: runtimeEnvironment,
  }
}
