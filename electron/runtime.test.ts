import path from 'node:path'
import {describe, expect, it} from 'vitest'
import {rejectPendingBackendRequests, resolveBackendLaunch} from './runtime'

describe('Electron backend runtime', () => {
  it('uses only the staged backend and browser in a Windows package', () => {
    const launch = resolveBackendLaunch({
      appPath: 'C:\\Program Files\\Peaks\\resources\\app.asar',
      environment: {
        PEAKS_PYTHON: 'C:\\untrusted\\python.exe',
        PEAKS_PACKAGING_BROWSER_SMOKE: '1',
        PLAYWRIGHT_BROWSERS_PATH: 'C:\\untrusted\\browsers',
        PYTHONHOME: 'C:\\untrusted\\home',
        PYTHONPATH: 'C:\\untrusted\\modules',
      },
      isPackaged: true,
      platform: 'win32',
      resourcesPath: 'C:\\Program Files\\Peaks\\resources',
      virtualenvExists: () => false,
    })

    expect(launch.command).toBe(
      path.win32.join('C:\\Program Files\\Peaks\\resources', 'backend', 'PeaksBridge.exe'),
    )
    expect(launch.args).toEqual([])
    expect(launch.environment.PLAYWRIGHT_BROWSERS_PATH).toBe(
      path.win32.join('C:\\Program Files\\Peaks\\resources', 'patchright-browsers'),
    )
    expect(launch.environment.PEAKS_PYTHON).toBeUndefined()
    expect(launch.environment.PEAKS_PACKAGING_BROWSER_SMOKE).toBeUndefined()
    expect(launch.environment.PYTHONHOME).toBeUndefined()
    expect(launch.environment.PYTHONPATH).toBeUndefined()
    expect(launch.environment.PYTHONIOENCODING).toBe('utf-8')
    expect(launch.environment.PYTHONUTF8).toBe('1')
  })

  it('uses the repository virtualenv and source package in development', () => {
    const appPath = 'C:\\workspace\\peaks'
    const launch = resolveBackendLaunch({
      appPath,
      environment: {},
      isPackaged: false,
      platform: 'win32',
      resourcesPath: path.win32.join(appPath, 'resources'),
      virtualenvExists: () => true,
    })

    expect(launch.command).toBe(path.win32.join(appPath, '.venv', 'Scripts/python.exe'))
    expect(launch.args).toEqual(['-m', 'peaks.bridge'])
    expect(launch.environment.PYTHONPATH).toBe(path.win32.join(appPath, 'src'))
    expect(launch.environment.PYTHONIOENCODING).toBe('utf-8')
    expect(launch.environment.PYTHONUTF8).toBe('1')
  })

  it('rejects and clears requests when spawning fails without an exit event', () => {
    const failures: string[] = []
    const pending = new Map([
      [1, {reject: (error: Error) => failures.push(error.message)}],
      [2, {reject: (error: Error) => failures.push(error.message)}],
    ])

    rejectPendingBackendRequests(pending, new Error('Peaks service could not start'))

    expect(failures).toEqual([
      'Peaks service could not start',
      'Peaks service could not start',
    ])
    expect(pending.size).toBe(0)
  })
})
