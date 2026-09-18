import {mkdtempSync, readFileSync, rmSync} from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import {afterEach, describe, expect, it, vi} from 'vitest'
import {DiscordPresence, PEAKS_DISCORD_APPLICATION_ID, readDiscordConfig, updateDiscordConfig} from './discordPresence'
import {DISCORD_PEAKS_IMAGE} from './discordActivity'
import {DiscordActivityHeartbeat} from './discordActivityHeartbeat'

const folders: string[] = []
const services: DiscordPresence[] = []
const heartbeats: DiscordActivityHeartbeat[] = []
const snapshot = () => ({locked: false, gameDetected: true, settings: {streamerMode: false}, currentMatch: {
  phase: 'live', game: 'VALORANT', map: 'Ascent', mode: 'Competitive', partySize: 2,
  teams: [{score: 9, players: [{self: true, agent: 'Omen', stats: {kills: 16, deaths: 9}}]}, {score: 5, players: []}],
}})
type LeagueClientGame = 'League of Legends' | 'Teamfight Tactics'
type SessionPhase = 'lobby' | 'matchmaking' | 'readycheck' | 'pregame' | 'live'
const leagueClientSnapshot = (game: LeagueClientGame, phase: SessionPhase = 'live') => ({
  locked: false, gameDetected: true, settings: {streamerMode: false},
  currentMatch: {
    game, phase, id: 'private-match-id', elapsed: '21:34', partySize: 2,
    map: game === 'League of Legends' ? "Summoner's Rift" : 'Teamfight Tactics',
    queue: game === 'League of Legends' ? '420' : '1160',
    mode: game === 'League of Legends' ? 'Ranked Solo/Duo' : 'Double Up',
    partyMax: game === 'League of Legends' ? 2 : 8,
    teams: [{name: 'Your team', players: [{
      self: true, name: 'PrivateUser#Secret', puuid: 'private-player-subject',
      agent: game === 'League of Legends' ? 'Ahri' : undefined,
      stats: game === 'League of Legends' ? {kills: 8, deaths: 3, assists: 6} : {health: 76},
      overallStats: {kills: 999, deaths: 888, assists: 777, health: 123},
    }]}, {name: 'Opponents', players: [{
      self: false, name: 'PrivateOpponent#Secret', agent: 'Omen',
      stats: {kills: 555, deaths: 444, assists: 333, health: 122},
    }]}],
  },
})
function setup(preview = false) {
  const folder = mkdtempSync(path.join(os.tmpdir(), 'peaks-discord-test-'))
  folders.push(folder)
  const filename = path.join(folder, 'discord.json')
  const client = {setActivity: vi.fn(), dispose: vi.fn()}
  const factory = vi.fn(() => client)
  const service = new DiscordPresence(filename, preview, PEAKS_DISCORD_APPLICATION_ID, factory)
  services.push(service)
  return {service, client, factory, filename}
}
afterEach(() => {
  heartbeats.splice(0).forEach(heartbeat => heartbeat.dispose())
  services.splice(0).forEach(service => service.dispose())
  folders.splice(0).forEach(folder => rmSync(folder, {recursive: true, force: true}))
  vi.useRealTimers()
})

describe('Discord presence preferences and lifecycle', () => {
  it('ships the supplied public application ID and accepts only bounded public preferences', () => {
    const initial = {enabled: true, applicationId: PEAKS_DISCORD_APPLICATION_ID}
    expect(readDiscordConfig(path.join(os.tmpdir(), 'peaks-no-such-discord-config'))).toEqual(initial)
    expect(updateDiscordConfig(initial, {enabled: false})).toEqual({...initial, enabled: false})
    expect(() => updateDiscordConfig(initial, {applicationId: 'a-token-or-secret'})).toThrow(/public/)
    expect(() => updateDiscordConfig(initial, {enabled: 'true'})).toThrow()
    expect(() => updateDiscordConfig(initial, {activity: {details: 'Injected'}})).toThrow()
  })

  it('never starts Discord or shares data in native demo mode', () => {
    const {service, factory} = setup(true)
    service.observe(snapshot())
    expect(service.getStatus().status).toBe('preview')
    expect(factory).not.toHaveBeenCalled()
  })

  it('projects only trusted current state and clears on lock, streamer mode and backend loss', () => {
    const {service, client} = setup()
    service.observe(snapshot())
    expect(client.setActivity).toHaveBeenLastCalledWith(expect.objectContaining({details: 'Carrying on Ascent'}))
    const count = client.setActivity.mock.calls.length
    service.observe({activity: {details: 'Renderer-controlled text'}})
    expect(client.setActivity).toHaveBeenCalledTimes(count)
    service.observe({...snapshot(), settings: {streamerMode: true}})
    expect(client.setActivity).toHaveBeenLastCalledWith(null)
    service.observe({state: {...snapshot(), locked: true}})
    expect(client.setActivity).toHaveBeenLastCalledWith(null)
    service.observe(snapshot())
    service.clear()
    expect(client.setActivity).toHaveBeenLastCalledWith(null)
  })

  it('updates every performance phrase directly from the self stats used by the Match column', () => {
    const {service, client} = setup()
    for (const [kills, deaths, phrase] of [
      [1, 9, 'Throwing'], [8, 9, 'Inting'], [10, 9, 'Trying'], [16, 9, 'Carrying'],
    ] as const) {
      const state = snapshot()
      state.currentMatch.teams[0].players[0].stats = {kills, deaths}
      // Exercise the wrapped backend result too, not just the pure builder.
      service.observe({state})
      expect(client.setActivity).toHaveBeenLastCalledWith(expect.objectContaining({
        details: `${phrase} on Ascent`, state: 'Competitive · 9:5 · Party 2/5',
        assets: {large_image: 'https://media.valorant-api.com/agents/8e253930-4c05-31dd-1b6c-968525494517/displayicon.png', large_text: 'Omen', small_image: DISCORD_PEAKS_IMAGE, small_text: 'Peaks'},
      }))
    }
  })

  it.each(['VALORANT', 'League of Legends', 'Teamfight Tactics'] as const)(
    'keeps the %s clock and connection while stats, artwork, elapsed time and party size update', game => {
      vi.useFakeTimers()
      vi.setSystemTime(new Date('2026-09-18T12:00:00Z'))
      const {service, client, factory} = setup()
      const state = game === 'VALORANT' ? snapshot() : leagueClientSnapshot(game)
      service.observe(state)
      const original = client.setActivity.mock.calls.at(-1)![0]
      expect(original.timestamps.start).toBe(Math.floor(Date.now() / 1000) - (game === 'VALORANT' ? 0 : 21 * 60 + 34))
      vi.advanceTimersByTime(30_000)
      const updated = {...state, currentMatch: {
        ...state.currentMatch, elapsed: '22:04', partySize: 3,
        teams: [{score: 10, players: [{self: true, agent: 'Jett', stats: {kills: 20, deaths: 9, assists: 8, health: 48}}]}, {score: 5, players: []}],
      }}
      service.observe({state: updated})
      const next = client.setActivity.mock.calls.at(-1)![0]
      expect(next.timestamps).toEqual(original.timestamps)
      expect(next.state).not.toEqual(original.state)
      expect(client.setActivity.mock.calls.slice(1).every(([activity]) => activity !== null)).toBe(true)
      service.handle({enabled: true, applicationId: PEAKS_DISCORD_APPLICATION_ID})
      expect(factory).toHaveBeenCalledOnce()
      expect(client.dispose).not.toHaveBeenCalled()
    },
  )

  it('keeps a late or temporarily missing match ID from restarting the same clock, but resets for a new match', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-09-18T12:00:00Z'))
    const {service, client} = setup()
    service.observe(snapshot())
    const start = client.setActivity.mock.calls.at(-1)![0].timestamps.start
    vi.advanceTimersByTime(15_000)
    service.observe({...snapshot(), currentMatch: {...snapshot().currentMatch, id: 'match-one'}})
    expect(client.setActivity.mock.calls.at(-1)![0].timestamps.start).toBe(start)
    vi.advanceTimersByTime(15_000)
    service.observe(snapshot())
    expect(client.setActivity.mock.calls.at(-1)![0].timestamps.start).toBe(start)
    vi.advanceTimersByTime(15_000)
    service.observe({...snapshot(), currentMatch: {...snapshot().currentMatch, id: 'match-two'}})
    expect(client.setActivity.mock.calls.at(-1)![0].timestamps.start).toBe(start + 45)
    expect(JSON.stringify(client.setActivity.mock.calls)).not.toContain('match-one')
    expect(JSON.stringify(client.setActivity.mock.calls)).not.toContain('match-two')
  })

  it('resumes the same clock after stale data but starts a new clock after a privacy clear or phase change', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-09-18T12:00:00Z'))
    const {service, client} = setup()
    service.observe(snapshot())
    const start = client.setActivity.mock.calls.at(-1)![0].timestamps.start
    service.observe({...snapshot(), currentMatch: {...snapshot().currentMatch, isStale: true}})
    expect(client.setActivity).toHaveBeenLastCalledWith(null)
    vi.advanceTimersByTime(65_000)
    service.observe(snapshot(), service.captureSnapshotEpoch())
    expect(client.setActivity.mock.calls.at(-1)![0].timestamps.start).toBe(start)
    service.clear()
    service.observe(snapshot())
    expect(client.setActivity.mock.calls.at(-1)![0].timestamps.start).toBe(start + 65)
    vi.advanceTimersByTime(10_000)
    service.observe({...snapshot(), currentMatch: {...snapshot().currentMatch, phase: 'pregame'}})
    expect(client.setActivity.mock.calls.at(-1)![0].timestamps.start).toBe(start + 75)
  })

  it('replaces VALORANT activity throughout League and TFT sessions without carrying old facts forward', () => {
    const {service, client, factory} = setup()
    service.observe(snapshot())
    expect(client.setActivity).toHaveBeenLastCalledWith(expect.objectContaining({details: 'Carrying on Ascent'}))

    for (const game of ['League of Legends', 'Teamfight Tactics'] as const) {
      for (const [phase, status] of [
        ['lobby', 'In lobby'], ['matchmaking', 'Finding a match'], ['readycheck', 'Match found'],
        ['pregame', game === 'League of Legends' ? 'Champion select' : 'Getting ready'], ['live', '21:34'],
      ] as const) {
        service.observe({state: leagueClientSnapshot(game, phase)})
        const activity = client.setActivity.mock.calls.at(-1)?.[0]
        expect(activity).toEqual(expect.objectContaining({
          type: 0,
          state: expect.stringContaining(status),
          assets: expect.objectContaining({small_image: DISCORD_PEAKS_IMAGE, small_text: 'Peaks'}),
          party: {size: game === 'League of Legends' ? [2, 2] : [2, 8]},
        }))
        expect(activity.state).toContain(game === 'League of Legends' ? 'Ranked Solo/Duo' : 'Double Up')
        expect(JSON.stringify({...activity, timestamps: undefined})).not.toMatch(/Ascent|Omen|VALORANT|private-|PrivateUser|PrivateOpponent|Secret|999|888|777|555|444|333/)
        if (phase !== 'live') expect(activity.state).not.toMatch(/KDA|HP|21:34/)
      }
    }

    expect(factory).toHaveBeenCalledOnce()
    service.observe({...leagueClientSnapshot('Teamfight Tactics'), gameDetected: false, currentMatch: null})
    expect(client.setActivity).toHaveBeenLastCalledWith(null)
    service.observe(snapshot())
    expect(client.setActivity).toHaveBeenLastCalledWith(expect.objectContaining({details: 'Carrying on Ascent'}))
  })

  it.each(['League of Legends', 'Teamfight Tactics'] as const)(
    'clears %s on stale matches, streamer mode, lock and backend loss', game => {
      const {service, client} = setup()
      const fresh = leagueClientSnapshot(game)
      service.observe(fresh)
      expect(client.setActivity.mock.calls.at(-1)?.[0]).not.toBeNull()
      service.observe({...fresh, currentMatch: {...fresh.currentMatch, isStale: true}})
      expect(client.setActivity).toHaveBeenLastCalledWith(null)

      service.observe(fresh)
      service.observe({...fresh, settings: {streamerMode: true}})
      expect(client.setActivity).toHaveBeenLastCalledWith(null)
      expect(service.canRefreshActivity()).toBe(false)

      service.observe(fresh)
      const beforeLock = service.captureSnapshotEpoch()
      service.observe({locked: true})
      service.observe(fresh, beforeLock)
      expect(client.setActivity).toHaveBeenLastCalledWith(null)
      expect(service.canRefreshActivity()).toBe(false)

      service.observe(fresh)
      service.clear()
      expect(client.setActivity).toHaveBeenLastCalledWith(null)
      expect(service.canRefreshActivity()).toBe(false)
    },
  )

  it.each(['League of Legends', 'Teamfight Tactics'] as const)(
    'expires %s and rejects delayed replies before resuming with a fresh session', game => {
      vi.useFakeTimers()
      const {service, client} = setup()
      service.observe(leagueClientSnapshot(game))
      const oldEpoch = service.captureSnapshotEpoch()
      vi.advanceTimersByTime(65_000)
      expect(client.setActivity).toHaveBeenLastCalledWith(null)
      expect(service.canRefreshActivity()).toBe(true)
      service.observe(leagueClientSnapshot(game), oldEpoch)
      expect(client.setActivity).toHaveBeenLastCalledWith(null)
      service.observe(leagueClientSnapshot(game, 'lobby'), service.captureSnapshotEpoch())
      expect(client.setActivity).toHaveBeenLastCalledWith(expect.objectContaining({state: expect.stringContaining('In lobby')}))
    },
  )

  it('keeps sharing disabled across game changes and publishes only the latest session on opt-in', () => {
    const {service, client, factory} = setup()
    service.observe(snapshot())
    service.handle({enabled: false})
    const count = client.setActivity.mock.calls.length
    service.observe(leagueClientSnapshot('League of Legends'))
    service.observe(leagueClientSnapshot('Teamfight Tactics', 'matchmaking'))
    expect(client.setActivity).toHaveBeenCalledTimes(count)
    expect(factory).toHaveBeenCalledOnce()
    expect(service.canRefreshActivity()).toBe(false)

    service.handle({enabled: true})
    expect(factory).toHaveBeenCalledTimes(2)
    expect(client.setActivity).toHaveBeenLastCalledWith(expect.objectContaining({
      details: 'Playing Teamfight Tactics', state: expect.stringContaining('Finding a match'),
    }))
    expect(JSON.stringify(client.setActivity.mock.calls.at(-1)?.[0])).not.toMatch(/Ahri|Ascent|KDA|HP/)
  })

  it('never creates a transport for League or TFT preview sessions', () => {
    const {service, factory} = setup(true)
    service.observe(leagueClientSnapshot('League of Legends'))
    service.observe(leagueClientSnapshot('Teamfight Tactics'))
    expect(service.getStatus().status).toBe('preview')
    expect(service.canRefreshActivity()).toBe(false)
    expect(factory).not.toHaveBeenCalled()
  })

  it('expires stale publication while allowing a fresh native recovery request', () => {
    vi.useFakeTimers()
    const {service, client} = setup()
    service.observe(snapshot())
    vi.advanceTimersByTime(65_000)
    expect(client.setActivity).toHaveBeenLastCalledWith(null)
    expect(service.canRefreshActivity()).toBe(true)
  })

  it('allows the native heartbeat only for unlocked sharing sessions', () => {
    const {service} = setup()
    expect(service.canRefreshActivity()).toBe(false)
    service.observe(snapshot())
    expect(service.canRefreshActivity()).toBe(true)
    service.observe({...snapshot(), settings: {streamerMode: true}})
    expect(service.canRefreshActivity()).toBe(false)
    service.observe(snapshot())
    service.handle({enabled: false})
    expect(service.canRefreshActivity()).toBe(false)
    service.handle({enabled: true, applicationId: ''})
    expect(service.canRefreshActivity()).toBe(false)
    service.handle({applicationId: PEAKS_DISCORD_APPLICATION_ID})
    expect(service.canRefreshActivity()).toBe(true)
    service.clear()
    expect(service.canRefreshActivity()).toBe(false)
    const preview = setup(true).service
    preview.observe(snapshot())
    expect(preview.canRefreshActivity()).toBe(false)
  })

  it('rejects pre-clear replies without losing fresh lock and unlock responses', () => {
    const {service, client} = setup()
    service.observe(snapshot())
    const pendingEpoch = service.captureSnapshotEpoch()
    service.clear()
    const callsAfterClear = client.setActivity.mock.calls.length
    service.observe(snapshot(), pendingEpoch)
    expect(client.setActivity).toHaveBeenCalledTimes(callsAfterClear)
    expect(client.setActivity).toHaveBeenLastCalledWith(null)
    expect(() => service.handle({enabled: false})).toThrow(/Unlock/)

    // The privacy command is dispatched after clearing, so its own response
    // belongs to the new epoch and must still be consumed.
    const lockEpoch = service.captureSnapshotEpoch()
    service.observe({locked: true}, lockEpoch)
    expect(service.captureSnapshotEpoch()).toBeGreaterThan(lockEpoch)
    service.observe(snapshot(), lockEpoch)
    expect(client.setActivity).toHaveBeenLastCalledWith(null)

    service.observe(snapshot(), service.captureSnapshotEpoch())
    expect(client.setActivity).toHaveBeenLastCalledWith(expect.objectContaining({details: 'Carrying on Ascent'}))
  })

  it.each([{locked: true}, {state: {locked: true}}, {locked: true, settings: null}])(
    'clears and rejects preferences for a minimal locked snapshot %j', locked => {
      const {service, client} = setup()
      service.observe(snapshot())
      service.observe(locked)
      expect(client.setActivity).toHaveBeenLastCalledWith(null)
      expect(() => service.handle({enabled: false})).toThrow(/Unlock/)
    },
  )

  it('invalidates an in-flight snapshot when the freshness watchdog clears', () => {
    vi.useFakeTimers()
    const {service, client} = setup()
    service.observe(snapshot())
    const requestEpoch = service.captureSnapshotEpoch()
    vi.advanceTimersByTime(65_000)
    service.observe(snapshot(), requestEpoch)
    expect(client.setActivity).toHaveBeenLastCalledWith(null)
  })

  it('recovers through the native heartbeat after a slow bridge without waking the renderer', async () => {
    vi.useFakeTimers()
    const {service, client} = setup()
    service.observe(snapshot())
    const oldEpoch = service.captureSnapshotEpoch()
    let busy = true
    const refresh = vi.fn(async () => {
      const fresh = snapshot()
      fresh.currentMatch.map = 'Bind'
      service.observe(fresh, service.captureSnapshotEpoch())
    })
    heartbeats.push(new DiscordActivityHeartbeat({canRefresh: () => service.canRefreshActivity(), isBusy: () => busy, refresh}))
    await vi.advanceTimersByTimeAsync(65_000)
    expect(refresh).not.toHaveBeenCalled()
    expect(client.setActivity).toHaveBeenLastCalledWith(null)
    const recoveryEpoch = service.captureSnapshotEpoch()
    expect(recoveryEpoch).toBeGreaterThan(oldEpoch)
    service.observe(snapshot(), oldEpoch)
    expect(client.setActivity).toHaveBeenLastCalledWith(null)
    await vi.advanceTimersByTimeAsync(10_000)
    expect(service.captureSnapshotEpoch()).toBe(recoveryEpoch)
    busy = false
    await vi.advanceTimersByTimeAsync(5000)
    expect(refresh).toHaveBeenCalledOnce()
    expect(client.setActivity).toHaveBeenLastCalledWith(expect.objectContaining({details: 'Carrying on Bind'}))
  })

  it.each(['lock', 'backend-loss'])('revokes stale recovery after authoritative %s', async reason => {
    vi.useFakeTimers()
    const {service, client} = setup()
    service.observe(snapshot())
    await vi.advanceTimersByTimeAsync(65_000)
    const recoveryEpoch = service.captureSnapshotEpoch()
    expect(service.canRefreshActivity()).toBe(true)
    if (reason === 'lock') service.observe({locked: true})
    else service.clear()
    service.observe(snapshot(), recoveryEpoch)
    expect(service.canRefreshActivity()).toBe(false)
    expect(client.setActivity).toHaveBeenLastCalledWith(null)
    expect(() => service.handle({enabled: false})).toThrow(/Unlock/)
    const refresh = vi.fn(async () => undefined)
    heartbeats.push(new DiscordActivityHeartbeat({canRefresh: () => service.canRefreshActivity(), isBusy: () => false, refresh}))
    await vi.advanceTimersByTimeAsync(65_000)
    expect(refresh).not.toHaveBeenCalled()
  })

  it('persists preferences only while unlocked and disposes the connection on opt-out', () => {
    const {service, client, filename} = setup()
    expect(() => service.handle({enabled: false})).toThrow(/Unlock/)
    service.observe(snapshot())
    expect(service.handle({enabled: false}).status).toBe('disabled')
    expect(client.dispose).toHaveBeenCalledOnce()
    expect(JSON.parse(readFileSync(filename, 'utf8'))).toEqual({enabled: false, applicationId: PEAKS_DISCORD_APPLICATION_ID})
    expect(readDiscordConfig(filename).enabled).toBe(false)
  })
})
