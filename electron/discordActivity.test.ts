import {readFileSync} from 'node:fs'
import {describe, expect, it} from 'vitest'
import {buildDiscordActivity, DISCORD_AGENT_ASSETS, DISCORD_PEAKS_IMAGE, DISCORD_TFT_IMAGE} from './discordActivity'

const omenImage = 'https://media.valorant-api.com/agents/8e253930-4c05-31dd-1b6c-968525494517/displayicon.png'

const selfPlayer = (stats: unknown = {kills: 9, deaths: 9}) => ({
  name: 'PrivateIdentity#EU', riotId: 'PrivateIdentity#EU', self: true, agent: 'Omen', stats,
  partyId: 'private-party-id', overallStats: {kills: 400, deaths: 5},
})

function snapshot(stats: unknown = {kills: 9, deaths: 9}, match: Record<string, unknown> = {}) {
  return {
    locked: false,
    gameDetected: true,
    settings: {streamerMode: false},
    currentMatch: {
      game: 'VALORANT', phase: 'live', map: 'Ascent', mode: 'Competitive',
      id: 'private-match-id', accountId: 'private-account-id',
      teams: [
        {name: 'Opponents', score: 5, players: [{name: 'Opponent#EU', self: false, agent: 'Sova', stats: {kills: 40, deaths: 1}}]},
        {name: 'Your team', score: 9, players: [selfPlayer(stats)]},
      ],
      ...match,
    },
  }
}

function leagueSnapshot(tft = false, overrides: Record<string, unknown> = {}) {
  return snapshot(null, {
    game: tft ? 'Teamfight Tactics' : 'League of Legends',
    map: tft ? 'Teamfight Tactics' : "Summoner's Rift",
    queue: tft ? '1160' : '420',
    mode: tft ? 'Double Up' : 'Ranked Solo/Duo',
    elapsed: '21:34', partySize: 2, partyMax: tft ? 8 : 2,
    teams: [{score: 40, players: [{...selfPlayer({kills: 8, deaths: 3, assists: 6, health: 76}), agent: 'Ahri'}]}],
    ...overrides,
  })
}

describe('League and TFT Discord activity', () => {
  it('shows League champion, map and real live KDA with official artwork', () => {
    expect(buildDiscordActivity(leagueSnapshot())).toEqual({
      type: 0,
      details: "Ahri on Summoner's Rift",
      state: 'Ranked Solo/Duo · 8/3/6 KDA · 21:34 · Party 2/2',
      assets: {
        large_image: 'https://ddragon.leagueoflegends.com/cdn/16.18.1/img/champion/Ahri.png',
        large_text: 'Ahri · League of Legends',
        small_image: DISCORD_PEAKS_IMAGE, small_text: 'Peaks',
      },
      party: {size: [2, 2]},
    })
  })

  it('shows Double Up, real health and the entire allowed lobby capacity', () => {
    expect(buildDiscordActivity(leagueSnapshot(true))).toEqual({
      type: 0,
      details: 'Playing Teamfight Tactics',
      state: 'Double Up · 76 HP · 21:34 · Party 2/8',
      assets: {
        large_image: DISCORD_TFT_IMAGE, large_text: 'Teamfight Tactics',
        small_image: DISCORD_PEAKS_IMAGE, small_text: 'Peaks',
      },
      party: {size: [2, 8]},
    })
  })

  it.each([
    ['lobby', 'In lobby'], ['matchmaking', 'Finding a match'],
    ['readycheck', 'Match found'], ['pregame', 'Champion select'],
  ])('uses lifecycle %s without stale live KDA, HP or duration', (phase, expected) => {
    for (const tft of [false, true]) {
      const activity = buildDiscordActivity(leagueSnapshot(tft, {phase}))
      const status = tft && phase === 'pregame' ? 'Getting ready' : expected
      expect(activity?.state).toBe(`${tft ? 'Double Up' : 'Ranked Solo/Duo'} · ${status} · Party 2/${tft ? 8 : 2}`)
      if (phase !== 'pregame' || tft) expect(activity?.details).not.toContain('Ahri')
      if (phase === 'pregame' && !tft) expect(activity?.details).toBe("Ahri on Summoner's Rift")
    }
  })

  it.each(['finished', 'loading', '', null, undefined, {}, 'Live'])('clears unsupported lifecycle %j', phase => {
    for (const tft of [false, true]) expect(buildDiscordActivity(leagueSnapshot(tft, {phase}))).toBeNull()
  })

  it.each(['VALORANT ', 'League', 'TFT', 'PrivateIdentity#EU', null, {}])('never shares an unrecognized game identifier %j', game => {
    expect(buildDiscordActivity(leagueSnapshot(false, {game}))).toBeNull()
  })

  it.each([false, true])('preserves every privacy and freshness guard for TFT=%s', tft => {
    const state = leagueSnapshot(tft)
    for (const invalid of [
      {...state, locked: true}, {...state, locked: undefined}, {...state, gameDetected: false},
      {...state, settings: {streamerMode: true}}, {...state, settings: {streamerMode: 'false'}},
      leagueSnapshot(tft, {isStale: true}), leagueSnapshot(tft, {isStale: 'false'}),
    ]) expect(buildDiscordActivity(invalid)).toBeNull()
    expect(buildDiscordActivity(leagueSnapshot(tft, {streamerMode: true}))).not.toBeNull()
  })

  it.each([false, true])('requires exactly one visible self for personal stats and artwork, TFT=%s', tft => {
    for (const players of [[], [{...selfPlayer(), self: false}], [selfPlayer(), selfPlayer()], [{...selfPlayer(), hidden: true}]]) {
      const activity = buildDiscordActivity(leagueSnapshot(tft, {teams: [{players}], elapsed: undefined}))
      expect(activity?.state).toBe(`${tft ? 'Double Up' : 'Ranked Solo/Duo'} · In game · Party 2/${tft ? 8 : 2}`)
      expect(activity?.assets.large_image).toBe(tft ? DISCORD_TFT_IMAGE : 'https://ddragon.leagueoflegends.com/cdn/16.18.1/img/map/map11.png')
    }
  })

  it.each([
    [1090, 'Normal'], ['1100', 'Ranked'], ['1130', 'Hyper Roll'],
    [1150, 'Double Up'], ['1160', 'Double Up'], ['1110', 'Tutorial'],
    ['99999', 'TFT'],
  ])('uses TFT queue %s over conflicting old labels or duo hints', (queue, mode) => {
    const activity = buildDiscordActivity(leagueSnapshot(true, {queue, mode: 'Double Up', teamMode: 'duos'}))
    expect(activity?.state).toBe(`${mode} · 76 HP · 21:34 · Party 2/8`)
  })

  it.each(['Double Up', 'TFT_PAIRS', 'RANKED_TFT_DOUBLE_UP', 'pairs', 'double_up'])('recognizes Double Up %s without native queue metadata', mode => {
    expect(buildDiscordActivity(leagueSnapshot(true, {queue: undefined, mode}))?.state).toContain('Double Up ·')
  })

  it.each([[450, 'ARAM'], ['440', 'Ranked Flex'], ['490', 'Quickplay'], ['480', 'Swiftplay'], ['1710', 'Arena'], ['2400', 'ARAM: Mayhem']])('recognizes League queue %s', (queue, mode) => {
    expect(buildDiscordActivity(leagueSnapshot(false, {queue}))?.state).toContain(`${mode} ·`)
  })

  it.each([[0, '0'], [76, '76'], [150, '150'], [1000, '1000'], [73.26, '73.3']])('accepts measured TFT health %s without assuming a 100 HP ceiling', (health, text) => {
    const teams = [{players: [{...selfPlayer({health}), agent: 'TFT tactician'}]}]
    expect(buildDiscordActivity(leagueSnapshot(true, {teams}))?.state).toContain(`${text} HP`)
  })

  it.each([undefined, null, '76', -1, 1001, Infinity, NaN, false, {}])('omits absent or invalid TFT health %j', health => {
    const teams = [{players: [selfPlayer({health, kills: 10, deaths: 5, currentHealth: 76})]}]
    const activity = buildDiscordActivity(leagueSnapshot(true, {teams}))
    expect(activity?.state).not.toContain('HP')
    expect(activity?.state).not.toContain('KDA')
  })

  it('does not infer own HP from history, opponents, the team score or rendered text', () => {
    const teams = [{score: 76, players: [
      {...selfPlayer({}), overallStats: {health: 99}, score: '76 HP'},
      {...selfPlayer({health: 76}), self: false},
    ]}]
    expect(buildDiscordActivity(leagueSnapshot(true, {teams}))?.state).toBe('Double Up · 21:34 · Party 2/8')
  })

  it.each([{}, {kills: 8, deaths: 3}, {kills: 8, deaths: 3, assists: '6'}, {kills: 8, deaths: -1, assists: 6}])('omits incomplete or invalid League KDA %j', stats => {
    const teams = [{players: [{...selfPlayer(stats), agent: 'Ahri', score: '8 / 3 / 6'}]}]
    expect(buildDiscordActivity(leagueSnapshot(false, {teams}))?.state).toBe('Ranked Solo/Duo · 21:34 · Party 2/2')
  })

  it.each([undefined, null, 0, '8', 65, 1, Infinity])('does not invent TFT capacity from a duo or invalid partyMax %j', partyMax => {
    const activity = buildDiscordActivity(leagueSnapshot(true, {partyMax}))
    expect(activity?.state).toContain('Party of 2')
    expect(activity).not.toHaveProperty('party')
  })

  it('does not invent party membership from the Double Up roster', () => {
    const activity = buildDiscordActivity(leagueSnapshot(true, {partySize: undefined, teamMode: 'duos'}))
    expect(activity).not.toHaveProperty('party')
    expect(activity?.state).not.toContain('Party')
  })

  it.each(['00:01', '3:99', '-1:20', '1000:00', '21:34\nprivate', 'PrivateIdentity#EU', 2134, null])('drops invalid or account-controlled elapsed text %j', elapsed => {
    const activity = buildDiscordActivity(leagueSnapshot(false, {elapsed}))
    expect(activity?.state).toBe('Ranked Solo/Duo · 8/3/6 KDA · Party 2/2')
  })

  it('resolves champion names whose official asset IDs differ without raw URL interpolation', () => {
    for (const [name, asset] of [['Wukong', 'MonkeyKing'], ["Kai'Sa", 'Kaisa'], ['Nunu & Willump', 'Nunu'], ['Dr. Mundo', 'DrMundo']]) {
      const activity = buildDiscordActivity(leagueSnapshot(false, {teams: [{players: [{...selfPlayer({}), agent: name}]}]}))
      expect(activity?.assets.large_image).toBe(`https://ddragon.leagueoflegends.com/cdn/16.18.1/img/champion/${asset}.png`)
      expect(activity?.details).toBe(`${name} on Summoner's Rift`)
    }
  })

  it('does not publish names, account IDs, controls, arbitrary hosts or paths in either game', () => {
    for (const tft of [false, true]) {
      const input = leagueSnapshot(tft, {
        map: 'https://private.example/PrivateIdentity#EU', queue: undefined, mode: 'PrivateIdentity#EU',
        large_image: 'https://private.example/image.png', elapsed: 'PrivateIdentity#EU',
        teams: [{name: 'PrivateIdentity#EU', players: [{...selfPlayer({}), agent: 'Ahri\nPrivateIdentity#EU'}]}],
      })
      const serialized = JSON.stringify(buildDiscordActivity(input))
      for (const sensitive of ['PrivateIdentity', 'private.example', 'private-match-id', 'private-account-id', 'private-party-id', 'Ahri']) {
        expect(serialized).not.toContain(sensitive)
      }
    }
  })

  it.each([false, true])('is deterministic, immutable and bounded for TFT=%s', tft => {
    const input = leagueSnapshot(tft, {partySize: 64, partyMax: 64})
    const original = JSON.stringify(input)
    const activity = buildDiscordActivity(input)!
    expect(buildDiscordActivity(input)).toEqual(activity)
    expect(JSON.stringify(input)).toBe(original)
    expect(activity.details.length).toBeLessThanOrEqual(128)
    expect(activity.state.length).toBeLessThanOrEqual(128)
    expect(activity.assets.large_text!.length).toBeLessThanOrEqual(128)
  })
})

describe('Discord activity projection', () => {
  it.each([
    [1, 9, 'Throwing'], [0, 8, 'Throwing'], [2, 9, 'Inting'], [8, 9, 'Inting'],
    [9, 9, 'Trying'], [0, 0, 'Trying'], [15, 9, 'Trying'], [16, 9, 'Carrying'], [30, 2, 'Carrying'],
  ])('uses current self %i/%i as %s', (kills, deaths, label) => {
    expect(buildDiscordActivity(snapshot({kills, deaths}))?.details).toBe(`${label} on Ascent`)
  })

  it('uses the own-team score regardless of team ordering and emits native RPC fields', () => {
    const activity = buildDiscordActivity(snapshot({kills: 16, deaths: 9}, {partySize: 2}))
    expect(activity).toEqual({
      type: 0,
      details: 'Carrying on Ascent',
      state: 'Competitive · 9:5 · Party 2/5',
      assets: {large_image: omenImage, large_text: 'Omen', small_image: DISCORD_PEAKS_IMAGE, small_text: 'Peaks'},
      party: {size: [2, 5]},
    })
  })

  it.each([
    undefined, null, {}, {kills: 9}, {deaths: 9}, {kills: '16', deaths: 9},
    {kills: -1, deaths: 9}, {kills: 1.5, deaths: 9}, {kills: Infinity, deaths: 9},
    {kills: 1_001, deaths: 9}, {kills: 9, deaths: -1}, {kills: 9, deaths: NaN},
  ])('does not invent current performance from missing or invalid stats %j', stats => {
    // Explicitly override the fixture's default for the undefined case.
    const state = snapshot(null, {teams: [{score: 9, players: [{...selfPlayer(), stats, score: '16 / 9 / 2'}]}]})
    expect(buildDiscordActivity(state)?.details).toBe('Playing on Ascent')
  })

  it('ignores historical stats, rendered KDA strings, opponents, and nonboolean self flags', () => {
    const state = snapshot(null, {teams: [{players: [
      {...selfPlayer(), self: 'true', stats: {kills: 90, deaths: 0}},
      {...selfPlayer(null), score: '16 / 9 / 2'},
    ]}]})
    const activity = buildDiscordActivity(state)
    expect(activity?.details).toBe('Playing on Ascent')
    expect(activity?.state).toBe('Competitive')
  })

  it('requires a unique visible self before disclosing player-specific facts or a team score', () => {
    for (const players of [[], [{...selfPlayer(), self: false}], [selfPlayer(), selfPlayer()], [{...selfPlayer(), hidden: true}]]) {
      const activity = buildDiscordActivity(snapshot(null, {teams: [{score: 9, players}, {score: 5, players: []}]}))
      expect(activity?.details).toBe('Playing on Ascent')
      expect(activity?.state).toBe('Competitive')
      expect(activity?.assets).not.toHaveProperty('large_image')
    }
  })

  it('keeps own activity when an incognito opponent marks the roster private', () => {
    const state = snapshot(undefined, {streamerMode: true, teams: [
      {score: 9, players: [selfPlayer({kills: 16, deaths: 9})]},
      {score: 5, players: [{...selfPlayer({kills: 1, deaths: 20}), self: false, hidden: true}]},
    ]})
    const activity = buildDiscordActivity(state)
    expect(activity?.details).toBe('Carrying on Ascent')
    expect(activity?.state).toBe('Competitive · 9:5')
    expect(activity?.assets.large_image).toBe(omenImage)
    expect(JSON.stringify(activity)).not.toContain('PrivateIdentity')
    expect(buildDiscordActivity({...state, settings: {streamerMode: true}})).toBeNull()
  })

  it('uses safe pregame presence without stale performance or round scores', () => {
    const activity = buildDiscordActivity(snapshot({kills: 90, deaths: 0}, {phase: 'pregame', partySize: 5}))
    expect(activity?.details).toBe('Playing on Ascent')
    expect(activity?.state).toBe('Competitive · Agent select · Party 5/5')
    expect(activity?.party?.size).toEqual([5, 5])
  })

  it.each([undefined, null, 0, 21, -1, 2.5, '2', NaN])('omits invalid or absent party size %j', partySize => {
    const activity = buildDiscordActivity(snapshot(undefined, {partySize}))
    expect(activity).not.toHaveProperty('party')
    expect(activity?.state).not.toContain('Party')
  })

  it('never infers party size from teammates or shared party identifiers', () => {
    const activity = buildDiscordActivity(snapshot(undefined, {teams: [{players: [
      selfPlayer(), {...selfPlayer(), self: false}, {...selfPlayer(), self: false},
    ]}]}))
    expect(activity).not.toHaveProperty('party')
  })

  it.each([[2, 2], [3, 3], [5, 5], [6, 10], [16, 20]])('uses actual party capacity for %i of %i members', (partySize, partyMax) => {
    const activity = buildDiscordActivity(snapshot(null, {partySize, partyMax}))
    expect(activity?.party?.size).toEqual([partySize, partyMax])
    expect(activity?.state).toContain(`Party ${partySize}/${partyMax}`)
  })

  it.each([null, 0, 1, 21, 2.5, '5', NaN])('retains the known count without a contradictory or invalid party capacity %j', partyMax => {
    const activity = buildDiscordActivity(snapshot(null, {partySize: 2, partyMax}))
    expect(activity).not.toHaveProperty('party')
    expect(activity?.state).toContain('Party of 2')
  })

  it.each(['competitive', 'unrated', 'swiftplay', 'spikerush', 'hurm', 'premier'])('keeps the requested out-of-five display for ordinary queue %s', queue => {
    const activity = buildDiscordActivity(snapshot(null, {queue, partySize: 2}))
    expect(activity?.state).toContain('Party 2/5')
    expect(activity?.party?.size).toEqual([2, 5])
  })

  it.each(['deathmatch', 'retake', 'skirmish', 'gauntlet', 'custom', 'unknown-future-mode'])('does not invent a missing capacity for queue %s', queue => {
    const activity = buildDiscordActivity(snapshot(null, {queue, partySize: 2}))
    expect(activity?.state).toContain('Party of 2')
    expect(activity).not.toHaveProperty('party')
  })

  it.each([6, 10, 20])('retains a larger party count %i when capacity is unknown', partySize => {
    const activity = buildDiscordActivity(snapshot(null, {queue: 'competitive', partySize}))
    expect(activity?.state).toContain(`Party of ${partySize}`)
    expect(activity).not.toHaveProperty('party')
  })

  it('prefers an explicit capacity and the source FFA classification over the default', () => {
    expect(buildDiscordActivity(snapshot(null, {queue: 'competitive', partySize: 2, partyMax: 3}))?.party?.size).toEqual([2, 3])
    const freeForAll = buildDiscordActivity(snapshot(null, {queue: 'competitive', freeForAll: true, partySize: 2}))
    expect(freeForAll?.state).toContain('Party of 2')
    expect(freeForAll).not.toHaveProperty('party')
  })

  it('always uses the fixed public Peaks icon rather than a backend-supplied artwork URL', () => {
    const activity = buildDiscordActivity(snapshot(null, {small_image: 'https://private.example/identity', peaksImage: 'secret'}))
    expect(DISCORD_PEAKS_IMAGE).toBe('https://cdn.discordapp.com/app-icons/1549634813756178503/73d9f3fd3166763966ab9868db736ee1.png')
    expect(activity?.assets.small_image).toBe(DISCORD_PEAKS_IMAGE)
  })

  it('accepts an explicit solo party and canonical numeric score strings', () => {
    const activity = buildDiscordActivity(snapshot(undefined, {partySize: 1, teams: [
      {score: '9', players: [selfPlayer()]}, {score: '5', players: []},
    ]}))
    expect(activity?.state).toBe('Competitive · 9:5 · Party 1/5')
    expect(activity?.party?.size).toEqual([1, 5])
  })

  it.each([undefined, null, -1, 101, '09', '5 points', 3.5, NaN])('omits the entire round score when either side is invalid %j', score => {
    const activity = buildDiscordActivity(snapshot(undefined, {teams: [{score: 9, players: [selfPlayer()]}, {score, players: []}]}))
    expect(activity?.state).toBe('Competitive')
  })

  it.each([
    null, undefined, [], {},
    {...snapshot(), locked: true}, {...snapshot(), locked: undefined}, {...snapshot(), locked: 'false'},
    {...snapshot(), gameDetected: false}, {...snapshot(), gameDetected: 'true'},
    {...snapshot(), settings: {streamerMode: true}}, {...snapshot(), settings: {streamerMode: 'false'}},
    {...snapshot(), settings: null}, {...snapshot(), currentMatch: null},
    snapshot(undefined, {isStale: true}),
    snapshot(undefined, {isStale: 'false'}), snapshot(undefined, {game: 'Dota 2'}),
    snapshot(undefined, {phase: undefined}), snapshot(undefined, {phase: 'finished'}),
  ])('clears activity for private, absent, or invalid session state %j', state => {
    expect(buildDiscordActivity(state)).toBeNull()
  })

  it('accepts older settings snapshots without an optional Streamer Mode flag', () => {
    expect(buildDiscordActivity({...snapshot(), settings: {}})?.details).toBe('Trying on Ascent')
  })

  it('does not send unknown names, URLs, identifiers, or control characters to Discord', () => {
    const state = snapshot(undefined, {map: 'https://private.example/PrivateIdentity#EU', mode: 'PrivateIdentity#EU', teams: [{players: [{...selfPlayer(), agent: 'PrivateIdentity#EU'}]}]})
    const activity = buildDiscordActivity(state)
    expect(activity?.details).toBe('Trying in VALORANT')
    expect(activity?.state).toBe('VALORANT')
    expect(activity?.assets).toEqual({small_image: DISCORD_PEAKS_IMAGE, small_text: 'Peaks'})
    const serialized = JSON.stringify(activity)
    for (const sensitive of ['PrivateIdentity', 'private.example', 'private-match-id', 'private-account-id', 'private-party-id']) expect(serialized).not.toContain(sensitive)
    expect(buildDiscordActivity(snapshot(undefined, {map: 'Ascent\nsecret', mode: 'Competitive\nsecret'}))?.details).toBe('Trying in VALORANT')
  })

  it('ignores oversized and malformed rosters without unbounded traversal or inferred self', () => {
    for (const teams of [null, {}, Array.from({length: 33}, () => ({players: []})), [{players: Array.from({length: 65}, () => selfPlayer())}], [{players: [null]}]]) {
      const activity = buildDiscordActivity(snapshot(undefined, {teams}))
      expect(activity?.details).toBe('Playing on Ascent')
      expect(activity?.state).toBe('Competitive')
    }
  })

  it('retains the own agent in a 14-player Deathmatch without team scores or invented K/D', () => {
    const players = Array.from({length: 14}, (_, index) => ({...selfPlayer(null), self: index === 13}))
    const activity = buildDiscordActivity(snapshot(null, {queueId: 'deathmatch', freeForAll: true, teams: [{score: 40, players}]}))
    expect(activity?.details).toBe('Playing on Ascent')
    expect(activity?.state).toBe('Deathmatch')
    expect(activity?.assets.large_image).toBe(omenImage)
  })

  it('retains the own agent in eight duo teams and never invents a two-sided score', () => {
    const teams = Array.from({length: 8}, (_, index) => ({score: 9, players: [
      {...selfPlayer(null), self: index === 7}, {...selfPlayer(null), self: false},
    ]}))
    const activity = buildDiscordActivity(snapshot(null, {mode: 'Gauntlet: Glitched', teams, partySize: 2, partyMax: 2}))
    expect(activity?.details).toBe('Playing on Ascent')
    expect(activity?.state).toBe('Gauntlet: Glitched · Party 2/2')
    expect(activity?.assets.large_image).toBe(omenImage)
  })

  it.each([
    {freeForAll: true}, {queue: 'deathmatch'}, {queueId: 'deathmatch'},
    {modeId: '/Game/GameModes/Deathmatch/Deathmatch_GameMode.Deathmatch_GameMode'},
  ])('never treats two presentation buckets as FFA teams %j', mode => {
    const activity = buildDiscordActivity(snapshot(null, mode))
    expect(activity?.state).not.toContain('9:5')
    expect(activity?.assets.large_image).toBe(omenImage)
  })

  it.each([
    ['hurm', 'Team Deathmatch'], ['ggteam', 'Escalation'], ['retake', 'Retake'], ['skirmish', 'Skirmish'],
  ])('prefers the native queue %s to a less specific mode label', (queueId, label) => {
    expect(buildDiscordActivity(snapshot(null, {queueId, mode: 'deathmatch'}))?.state).toBe(`${label} · 9:5`)
  })

  it('reads the actual native queue field before aliases or asset mode paths', () => {
    const activity = buildDiscordActivity(snapshot(null, {
      queue: 'hurm', queueId: 'deathmatch', mode: 'Deathmatch',
      modeId: '/Game/GameModes/Deathmatch/Deathmatch_GameMode.Deathmatch_GameMode',
    }))
    expect(activity?.state).toBe('Team Deathmatch · 9:5')
  })

  it('bounds aggregate roster traversal across individually valid teams', () => {
    const teams = Array.from({length: 2}, (_, index) => ({players: Array.from({length: 33}, (_, player) => ({...selfPlayer(null), self: index === 1 && player === 32}))}))
    expect(buildDiscordActivity(snapshot(null, {teams}))?.assets).not.toHaveProperty('large_image')
  })

  it('resolves all bundled agent UUIDs and map paths without a packaged JSON dependency', () => {
    const metadata = JSON.parse(readFileSync(new URL('../src/peaks/ui/assets/riot/valorant/index.json', import.meta.url), 'utf8')) as {
      agents: Array<{displayName: string; uuid: string}>
      maps: Array<{displayName: string; uuid: string; mapUrl: string; path: string}>
    }
    expect(DISCORD_AGENT_ASSETS).toHaveLength(metadata.agents.length)
    for (const agent of metadata.agents) {
      const expectedKey = agent.displayName.toLowerCase().replace(/[^a-z0-9]+/g, '')
      expect(DISCORD_AGENT_ASSETS.find(entry => entry.uuid === agent.uuid)?.key).toBe(expectedKey)
      for (const alias of [agent.uuid, agent.displayName.toUpperCase(), expectedKey]) {
        const activity = buildDiscordActivity(snapshot(undefined, {teams: [{players: [{...selfPlayer(), agent: alias}]}]}))
        expect(activity?.assets.large_image).toBe(`https://media.valorant-api.com/agents/${agent.uuid}/displayicon.png`)
        expect(activity?.assets.large_text).toBe(agent.displayName)
      }
    }
    for (const map of metadata.maps) {
      for (const alias of [map.displayName, map.uuid, map.mapUrl, map.path, `riot/${map.path}`]) {
        expect(buildDiscordActivity(snapshot(undefined, {map: alias}))?.details).toBe(`Trying on ${map.displayName}`)
      }
    }
  })

  it('is deterministic, leaves its input unchanged, and bounds all outbound text', () => {
    const state = snapshot(undefined, {partySize: 5})
    const original = JSON.stringify(state)
    const activity = buildDiscordActivity(state)
    expect(buildDiscordActivity(state)).toEqual(activity)
    expect(JSON.stringify(state)).toBe(original)
    expect(activity!.details.length).toBeLessThanOrEqual(128)
    expect(activity!.state.length).toBeLessThanOrEqual(128)
  })
})
