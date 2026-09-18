import {mkdtempSync, readFileSync, rmSync, writeFileSync} from 'node:fs'
import {tmpdir} from 'node:os'
import path from 'node:path'
import {afterEach, describe, expect, it, vi} from 'vitest'
import {safeTelemetryEvent, TELEMETRY_ENDPOINT, Telemetry} from './telemetry'
import {BACKEND_COMMANDS} from './security'

const cleanups: (() => void)[] = []
afterEach(() => {for (const cleanup of cleanups.splice(0)) cleanup()})
function create(available = true) {
  const directory = mkdtempSync(path.join(tmpdir(), 'peaks-telemetry-'))
  const filename = path.join(directory, 'telemetry.json')
  const send = vi.fn<typeof fetch>().mockResolvedValue(new Response(null, {status: 202}))
  let time = 100_000
  const service = new Telemetry({filename, version: '0.3.0', platform: 'win32', available, send, now: () => time})
  cleanups.push(() => {service.dispose(); rmSync(directory, {recursive: true, force: true})})
  return {service, send, filename, tick: () => {time += 60_001}}
}

describe('optional bounded app diagnostics', () => {
  it('defaults off and sends nothing before explicit opt-in', async () => {
    const {service, send} = create()
    expect(service.getStatus()).toEqual({enabled: false, available: true})
    service.track('app.started')
    await service.flush()
    expect(send).not.toHaveBeenCalled()
  })
  it('only sends fixed fields to the fixed HTTPS relay without auth or redirects', async () => {
    const {service, send, filename} = create()
    service.handle({enabled: true})
    service.track('command.completed', {command: 'search', outcome: 'success', duration_ms: 1234, query: 'Private#EU', token: 'never-send', message: 'private error', puuid: 'identity'})
    await service.flush()
    expect(JSON.parse(readFileSync(filename, 'utf8'))).toEqual({enabled: true})
    const [url, init] = send.mock.calls[0]
    expect(url).toBe(TELEMETRY_ENDPOINT)
    expect(init).toMatchObject({redirect: 'error', credentials: 'omit', headers: {'Content-Type': 'application/json'}})
    expect(JSON.parse(init!.body as string)).toEqual({schema: 1, events: [
      {event: 'app.started', version: '0.3.0', platform: 'win32'},
      {event: 'command.completed', version: '0.3.0', platform: 'win32', command: 'search', outcome: 'success', duration_ms: 1200},
    ]})
  })
  it('rejects arbitrary names and prevents identifiers in enum-shaped fields', () => {
    expect(safeTelemetryEvent('private-user', {}, '0.3.0', 'win32')).toBeNull()
    expect(safeTelemetryEvent('app.started', {}, 'custom-private-build', 'win32')).toBeNull()
    expect(safeTelemetryEvent('app.started', {}, '0.3.0', 'hostname')).toBeNull()
    expect(safeTelemetryEvent('command.completed', {command: 'private-command', outcome: 'success'}, '0.3.0', 'win32')).toBeNull()
    expect(safeTelemetryEvent('update.state', {state: 'private-stacktrace'}, '0.3.0', 'win32')).toBeNull()
  })
  it('covers every exposed backend operation without copying sensitive fields', () => {
    for (const command of BACKEND_COMMANDS) {
      expect(safeTelemetryEvent('command.completed', {
        command, outcome: 'failure', duration_ms: 149,
        accountId: 'private-account', riotId: 'Private#EU', pin: '1234', code: '123456',
        token: 'private-token', cookies: {ssid: 'private-cookie'}, qrImage: 'private-image',
        error: new Error('private error'), payload: {key: 'private-api-key'},
      }, '0.3.0', 'win32')).toEqual({
        event: 'command.completed', version: '0.3.0', platform: 'win32',
        command, outcome: 'failure', duration_ms: 100,
      })
    }
  })
  it('records icon saves without collecting the account or icon preference', async () => {
    const {service, send} = create()
    service.handle({enabled: true})
    const payload = {
      accountId: 'private-account',
      icon: {game: 'VALORANT', characterId: 'private-character'},
    }
    const result = {accounts: [{id: payload.accountId, riotId: 'Private#EU', accountIcon: payload.icon}]}
    await expect(service.runCommand('set_account_icon', () => result)).resolves.toBe(result)
    service.track('command.completed', {command: 'set_account_icon', outcome: 'failure', ...payload, result})
    await service.flush()
    const events = JSON.parse(send.mock.calls[0][1]!.body as string).events
    expect(events.slice(1)).toEqual([
      {event: 'command.completed', version: '0.3.0', platform: 'win32', command: 'set_account_icon', outcome: 'success', duration_ms: 0},
      {event: 'command.completed', version: '0.3.0', platform: 'win32', command: 'set_account_icon', outcome: 'failure'},
    ])
    expect(JSON.stringify(events)).not.toMatch(/private-account|private-character|Private#EU|VALORANT|accountIcon/)
  })
  it.each(['copy_match_image', 'discord_presence', 'update_check', 'update_install', 'release_history', 'release_history_ack'])(
    'records native operation %s', command => {
      expect(safeTelemetryEvent('command.completed', {command, outcome: 'success'}, '0.3.0', 'win32')?.command).toBe(command)
    },
  )
  it('records synchronous preparation failures, asynchronous failures and success exactly once', async () => {
    const {service, send} = create()
    service.handle({enabled: true})
    const privateError = new Error('Private#EU token=private-token C:\\Users\\Private\\file')
    await expect(service.runCommand('connect_riot_qr_image', () => {throw privateError})).rejects.toBe(privateError)
    await expect(service.runCommand('import_session', () => Promise.reject(privateError))).rejects.toBe(privateError)
    const result = {code: '123456', token: 'private-token'}
    await expect(service.runCommand('copy_totp', () => result)).resolves.toBe(result)
    await service.flush()
    const events = JSON.parse(send.mock.calls[0][1]!.body as string).events
    expect(events.slice(1)).toEqual([
      {event: 'command.completed', version: '0.3.0', platform: 'win32', command: 'connect_riot_qr_image', outcome: 'failure', duration_ms: 0},
      {event: 'command.completed', version: '0.3.0', platform: 'win32', command: 'import_session', outcome: 'failure', duration_ms: 0},
      {event: 'command.completed', version: '0.3.0', platform: 'win32', command: 'copy_totp', outcome: 'success', duration_ms: 0},
    ])
    expect(JSON.stringify(events)).not.toMatch(/Private|private-token|123456/)
  })
  it('binds the whole operation to its initial consent, including asynchronous preparation', async () => {
    const {service, send} = create()
    let finish!: () => void
    const beforeOptIn = service.runCommand('add_account', () => new Promise<void>(resolve => {finish = resolve}))
    service.handle({enabled: true})
    finish()
    await beforeOptIn
    const oldConsent = service.runCommand('connect_riot_client', () => new Promise<void>(resolve => {finish = resolve}))
    service.handle({enabled: false})
    service.handle({enabled: true})
    finish()
    await oldConsent
    await service.runCommand('remove_account', () => undefined)
    await service.flush()
    expect(JSON.parse(send.mock.calls[0][1]!.body as string).events.map((event: {event: string; command?: string}) => event.command ?? event.event))
      .toEqual(['app.started', 'remove_account'])
  })
  it('throttles repeated activity and bounds numeric values', async () => {
    const {service, send, tick} = create()
    service.handle({enabled: true})
    for (let i = 0; i < 500; i++) service.track('command.completed', {command: 'activity', outcome: 'success', duration_ms: 9e9})
    await service.flush()
    const events = JSON.parse(send.mock.calls[0][1]!.body as string).events
    expect(events).toHaveLength(2)
    expect(events[1].duration_ms).toBe(300_000)
    tick()
    service.track('command.completed', {command: 'activity', outcome: 'success', duration_ms: NaN})
    await service.flush()
    expect(JSON.parse(send.mock.calls[1][1]!.body as string).events[0]).not.toHaveProperty('duration_ms')
  })
  it('drops pending data and aborts transport on opt-out', async () => {
    const {service, send} = create()
    let finish!: (response: Response) => void
    send.mockReturnValue(new Promise(resolve => {finish = resolve}))
    service.handle({enabled: true})
    const running = service.flush()
    service.track('backend.failed')
    service.handle({enabled: false})
    expect(send.mock.calls[0][1]!.signal!.aborted).toBe(true)
    finish(new Response(null, {status: 202}))
    await running
    await service.flush()
    expect(send).toHaveBeenCalledTimes(1)
  })
  it('excludes operations started before opt-in or across a consent change', async () => {
    const {service, send} = create()
    const beforeConsent = service.captureConsentEpoch()
    expect(beforeConsent).toBeNull()
    service.handle({enabled: true})
    service.track('command.completed', {command: 'search', outcome: 'success'}, beforeConsent)
    const previousConsent = service.captureConsentEpoch()
    service.handle({enabled: false})
    service.handle({enabled: true})
    service.track('command.completed', {command: 'player', outcome: 'success'}, previousConsent)
    const currentConsent = service.captureConsentEpoch()
    service.track('command.completed', {command: 'refresh', outcome: 'success'}, currentConsent)
    await service.flush()
    const events = JSON.parse(send.mock.calls[0][1]!.body as string).events
    expect(events.map((event: {event: string; command?: string}) => event.command ?? event.event)).toEqual(['app.started', 'refresh'])
  })
  it('keeps fresh opt-in events when an aborted older request finishes', async () => {
    const {service, send} = create()
    let finish!: (response: Response) => void
    send.mockReturnValueOnce(new Promise(resolve => {finish = resolve}))
    service.handle({enabled: true})
    const previous = service.flush()
    service.handle({enabled: false})
    service.handle({enabled: true})
    service.track('backend.started')
    expect(send.mock.calls[0][1]!.signal!.aborted).toBe(true)
    finish(new Response(null, {status: 202}))
    await previous
    await service.flush()
    expect(send).toHaveBeenCalledTimes(2)
    expect(JSON.parse(send.mock.calls[1][1]!.body as string).events.map((event: {event: string}) => event.event)).toEqual(['app.started', 'backend.started'])
  })
  it('does not transmit in development or demo even when enabled', async () => {
    const {service, send} = create(false)
    service.handle({enabled: true})
    service.track('backend.started')
    await service.flush()
    expect(send).not.toHaveBeenCalled()
  })
  it('handles network failure without retries or error payloads', async () => {
    const {service, send} = create()
    service.handle({enabled: true})
    send.mockRejectedValue(new Error('private transport context'))
    await expect(service.flush()).resolves.toBeUndefined()
    await service.flush()
    expect(send).toHaveBeenCalledTimes(1)
  })
  it('validates settings and treats malformed stored consent as off', () => {
    const {service, filename} = create()
    expect(() => service.handle({enabled: 'true'})).toThrow()
    expect(() => service.handle({endpoint: 'https://example.com'})).toThrow()
    expect(() => service.handle(null)).toThrow()
    writeFileSync(filename, '{broken')
    const second = new Telemetry({filename, version: '0.3.0', platform: 'win32', available: true})
    cleanups.push(() => second.dispose())
    expect(second.getStatus().enabled).toBe(false)
  })
})
