import {randomUUID} from 'node:crypto'
import net, {type Socket} from 'node:net'
import os from 'node:os'
import path from 'node:path'
import {afterEach, describe, expect, it, vi} from 'vitest'
import {DiscordIpcClient, discordPipePaths, encodeDiscordFrame} from './discordIpc'
import {buildDiscordActivity} from './discordActivity'

const clients: DiscordIpcClient[] = []
const servers: net.Server[] = []
const sockets: Socket[] = []
type Frame = {opcode: number; payload: Record<string, unknown>}
async function fakeDiscord(acknowledge = true) {
  const frames: Frame[] = []
  const ipcPath = process.platform === 'win32' ? `\\\\?\\pipe\\peaks-discord-test-${randomUUID()}` : path.join(os.tmpdir(), `peaks-discord-${randomUUID()}.sock`)
  const server = net.createServer(socket => {
    sockets.push(socket)
    let buffer: Buffer = Buffer.alloc(0)
    socket.on('data', chunk => {
      buffer = Buffer.concat([buffer, chunk])
      while (buffer.length >= 8 && buffer.length >= 8 + buffer.readUInt32LE(4)) {
        const opcode = buffer.readUInt32LE(0)
        const length = buffer.readUInt32LE(4)
        const payload = JSON.parse(buffer.subarray(8, 8 + length).toString('utf8'))
        buffer = buffer.subarray(8 + length)
        frames.push({opcode, payload})
        if (opcode === 0) {
          const response = encodeDiscordFrame(1, {cmd: 'DISPATCH', evt: 'READY', data: {user: {id: 'never-export'}}})
          // Deliberately split a header; the second write also contains a ping.
          socket.write(response.subarray(0, 3))
          socket.write(Buffer.concat([response.subarray(3), encodeDiscordFrame(3, {probe: true})]))
        } else if (opcode === 1 && acknowledge) socket.write(encodeDiscordFrame(1, {cmd: 'SET_ACTIVITY', nonce: payload.nonce, evt: null, data: null}))
      }
    })
    socket.on('error', () => undefined)
  })
  servers.push(server)
  await new Promise<void>((resolve, reject) => { server.once('error', reject); server.listen(ipcPath, resolve) })
  return {frames, ipcPath}
}
afterEach(async () => {
  clients.splice(0).forEach(client => client.dispose())
  sockets.splice(0).forEach(socket => socket.destroy())
  await Promise.all(servers.splice(0).map(server => new Promise<void>(resolve => server.close(() => resolve()))))
  vi.restoreAllMocks()
})

describe('Discord native IPC', () => {
  it('uses only Discord local named pipes and runtime sockets', () => {
    expect(discordPipePaths('win32', {})).toHaveLength(10)
    expect(discordPipePaths('win32', {})[0]).toBe('\\\\?\\pipe\\discord-ipc-0')
    expect(discordPipePaths('linux', {XDG_RUNTIME_DIR: '/run/user/1000'})[9]).toBe(path.join('/run/user/1000', 'discord-ipc-9'))
  })

  it('handshakes, handles fragmented frames and ping, deduplicates updates, and clears immediately', async () => {
    const {frames, ipcPath} = await fakeDiscord()
    const statuses = vi.fn()
    const client = new DiscordIpcClient('1549634813756178503', statuses, [ipcPath])
    clients.push(client)
    const activity = buildDiscordActivity({locked: false, gameDetected: true, settings: {}, currentMatch: {
      phase: 'live', game: 'VALORANT', map: 'Ascent', teams: [{players: [{self: true, agent: 'Omen', stats: {kills: 1, deaths: 9}}]}],
    }})!
    client.setActivity(activity)
    await vi.waitFor(() => expect(frames.filter(frame => frame.opcode === 1)).toHaveLength(1))
    expect(frames[0]).toEqual({opcode: 0, payload: {v: 1, client_id: '1549634813756178503'}})
    expect(frames.find(frame => frame.opcode === 4)?.payload).toEqual({probe: true})
    expect(frames.find(frame => frame.opcode === 1)?.payload.args).toEqual({pid: process.pid, activity})
    client.setActivity(activity)
    expect(frames.filter(frame => frame.opcode === 1)).toHaveLength(1)
    client.setActivity(null)
    await vi.waitFor(() => expect(frames.filter(frame => frame.opcode === 1)).toHaveLength(2))
    expect(frames.filter(frame => frame.opcode === 1)[1].payload.args).toEqual({pid: process.pid, activity: null})
    expect(JSON.stringify(statuses.mock.calls)).not.toContain('never-export')
  })

  it('rejects oversized frames without parsing their payload', async () => {
    const {ipcPath} = await fakeDiscord()
    const statuses = vi.fn()
    clients.push(new DiscordIpcClient('1549634813756178503', statuses, [ipcPath]))
    await vi.waitFor(() => expect(statuses).toHaveBeenCalledWith('connected', expect.any(String)))
    const header = Buffer.alloc(8)
    header.writeUInt32LE(1, 0)
    header.writeUInt32LE(100_000, 4)
    sockets.at(-1)!.write(header)
    await vi.waitFor(() => expect(statuses).toHaveBeenCalledWith('error', 'Discord sent an invalid response.'))
  })

  it('does not report a queued activity as shared when Discord only acknowledged a clear', async () => {
    const {frames, ipcPath} = await fakeDiscord(false)
    const statuses = vi.fn()
    const client = new DiscordIpcClient('1549634813756178503', statuses, [ipcPath])
    clients.push(client)
    await vi.waitFor(() => expect(frames.filter(frame => frame.opcode === 1)).toHaveLength(1))
    const clear = frames.find(frame => frame.opcode === 1)!
    client.setActivity(buildDiscordActivity({locked: false, gameDetected: true, settings: {}, currentMatch: {
      phase: 'live', game: 'VALORANT', map: 'Ascent', teams: [{players: [{self: true, agent: 'Omen'}]}],
    }}))
    sockets.at(-1)!.write(encodeDiscordFrame(1, {cmd: 'SET_ACTIVITY', nonce: clear.payload.nonce, evt: null}))
    await vi.waitFor(() => expect(statuses).toHaveBeenLastCalledWith('connected', 'Connected. Waiting for a supported game session.'))
    expect(frames.filter(frame => frame.opcode === 1)).toHaveLength(1)
  })
})
