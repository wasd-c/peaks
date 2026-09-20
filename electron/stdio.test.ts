import {spawn} from 'node:child_process'
import {EventEmitter} from 'node:events'
import {describe, expect, it} from 'vitest'
import {protectStdio} from './stdio'

function writeAfterLauncherDisconnect(protectedOutput: boolean): Promise<string[]> {
  return new Promise((resolve, reject) => {
    const child = spawn(process.execPath, ['-e', `
      const {Console} = require('node:console');
      const failures = [];
      process.on('uncaughtException', error => failures.push(error.code));
      if (${protectedOutput}) (${protectStdio.toString()})();
      const logger = new Console({stdout: process.stdout, stderr: process.stderr, ignoreErrors: false});
      process.once('message', async () => {
        for (let index = 0; index < 3; index++) {
          logger.info('Background activity');
          logger.error('Expected IPC rejection: game unavailable');
          await new Promise(resolve => setTimeout(resolve, 20));
        }
        process.send({failures}, () => process.disconnect());
      });
      process.send('ready');
    `], {stdio: ['ignore', 'pipe', 'pipe', 'ipc'], windowsHide: true})
    const timer = setTimeout(() => {
      child.kill()
      reject(new Error('Disconnected console regression timed out'))
    }, 5000)
    let failures: string[] | undefined
    child.on('error', error => { clearTimeout(timer); reject(error) })
    child.on('message', message => {
      if (message === 'ready') {
        child.stdout!.destroy()
        child.stderr!.destroy()
        child.send('write')
      } else if (message && typeof message === 'object' && 'failures' in message) {
        failures = message.failures as string[]
      }
    })
    child.on('exit', code => {
      clearTimeout(timer)
      if (code === 0 && failures) resolve(failures)
      else reject(new Error(`Disconnected console child failed: ${code}`))
    })
  })
}

describe('main-process console pipes', () => {
  it('survives repeated console writes after the launcher closes both real pipes', async () => {
    expect(await writeAfterLauncherDisconnect(false)).toContain('EPIPE')
    expect(await writeAfterLauncherDisconnect(true)).toEqual([])
  })

  it('keeps unrelated stream failures visible and can remove its listeners', () => {
    const stdout = new EventEmitter(), stderr = new EventEmitter()
    const dispose = protectStdio([stdout, stderr])
    const unrelated = Object.assign(new Error('Other I/O failure'), {code: 'EIO'})
    expect(() => stdout.emit('error', unrelated)).toThrow(unrelated)
    expect(() => stderr.emit('error', unrelated)).toThrow(unrelated)
    dispose()
    expect(stdout.listenerCount('error')).toBe(0)
    expect(stderr.listenerCount('error')).toBe(0)
  })
})
