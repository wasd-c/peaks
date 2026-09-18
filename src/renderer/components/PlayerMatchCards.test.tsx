import {renderToStaticMarkup} from 'react-dom/server'
import {LayerProvider} from '@astryxdesign/core/Layer'
import {describe, expect, it} from 'vitest'
import {PlayerMatchCards} from './PlayerMatchCards'
import {historicalPerformanceTags, playerPerformanceTags} from '../matchAnalytics'
import type {Game, MatchPlayer, MatchTeam, SessionPhase} from '../types'

const player = (index: number): MatchPlayer => ({
  name: `Player${index}#EU`, riotId: `Player${index}#EU`, agent: 'Omen',
  accountLevel: 200, currentRank: 'Ascendant 2', peakRank: 'Immortal 1', peakRankSeason: 'V26:A1',
  overallStats: {matchesPlayed: 5, kills: 90, deaths: 60, assists: 40, roundsPlayed: 100, combatScore: 24000},
})
const render = (teams: MatchTeam[], completed = false, options: {game?: Game; phase?: SessionPhase; mode?: string; queueId?: string; teamMode?: 'duos'; freeForAll?: boolean; allowReorder?: boolean; fitToHeight?: boolean} = {}) => renderToStaticMarkup(
  <LayerProvider><PlayerMatchCards teams={teams} game="VALORANT" label={completed ? 'Completed match' : 'Live match'} completed={completed} allowReorder={!completed} onSelectPlayer={() => undefined} {...options} /></LayerProvider>,
)

const cardNames = (html: string) => [...html.matchAll(/<div\b[^>]*\bclass="[^"]*\bpmc-card\b[^"]*"[^>]*>/g)]
  .map(([tag]) => tag.match(/aria-label="([^",]*)/)?.[1])

const statisticCells = (html: string, label: string) => {
  const rows = [...html.matchAll(/<div\b[^>]*role="row"[^>]*>/g)]
  for (const [index, start] of rows.entries()) {
    const row = html.slice(start.index, rows[index + 1]?.index)
    const cells = [...row.matchAll(/<(?:span|div)\b([^>]*role="(?:rowheader|cell)"[^>]*)>([\s\S]*?)<\/(?:span|div)>/g)]
      .map(([, attributes, content]) => attributes.includes('aria-label="Loading"') ? 'Loading' : content.replace(/<[^>]+>/g, ''))
    if (cells[0] === label) return cells.slice(1)
  }
  return undefined
}

describe('player match cards', () => {
  it.each([false, true])('preserves all ten identities and essential stats in a fitted roster, completed=%s', completed => {
    const teams = Array.from({length: 2}, (_, team) => ({name: `Team ${team}`, players: Array.from({length: 5}, (_, index) => ({...player(team * 5 + index), stats: {kills: 12, deaths: 9, assists: 4, combatScore: 4000, roundsPlayed: 20}}))}))
    const html = render(teams, completed, {fitToHeight: true})
    expect(cardNames(html)).toHaveLength(10)
    expect(html).toContain('pmc-lineup--fit')
    expect(statisticCells(html, 'K/D/A')).toEqual(['12 / 9 / 4'])
    expect(statisticCells(html, 'K/D')).toEqual(['1.5', '1.33'])
    expect(statisticCells(html, 'ACS')).toEqual(['240', '200'])
    expect(statisticCells(html, 'Kills')).toBeUndefined()
    expect(html.includes('draggable="true"')).toBe(!completed)
  })

  it('keeps historical averages and an animated loading state distinct from live KDA in a fitted roster', () => {
    const historical = render([{name: 'Blue', players: [player(0)]}, {name: 'Red', players: [player(1)]}], false, {fitToHeight: true, phase: 'pregame'})
    expect(statisticCells(historical, 'Overall K/D/A')).toEqual(['18 / 12 / 8'])
    const loading = render([{name: 'Blue', players: [{name: 'Loading#EU', statsLoading: true}]}, {name: 'Red', players: [{name: 'Hidden', hidden: true}]}], false, {fitToHeight: true})
    expect(statisticCells(loading, 'Overall K/D/A')).toEqual(['Loading'])
    expect(loading).not.toContain('0 / 0 / 0')
    expect(loading).toContain('pmc-stat-skeleton')
  })
  it.each([0, 76, 130])('renders actual TFT health %i without treating it as historical data', health => {
    const html = render([{name: 'Players', players: [{name: 'Self#TEST', self: true, stats: {health}}]}], false, {game: 'Teamfight Tactics', phase: 'live'})
    expect(statisticCells(html, 'HP')).toEqual(['—', String(health)])
    const lobby = render([{name: 'Party', players: [{name: 'Self#TEST', self: true, stats: {health}}]}], false, {game: 'Teamfight Tactics', phase: 'lobby'})
    expect(statisticCells(lobby, 'HP')).toBeUndefined()
  })

  it('shows periodic TFT stats without turning current standing into a final placement or filling absent fields', () => {
    const teams = [{name: 'Players', players: [{name: 'Self#TEST', self: true, stats: {health: 73, standing: 3, boardUnits: 6, observedAt: 1_800_000_000}}]}]
    const html = render(teams, false, {game: 'Teamfight Tactics', phase: 'live'})
    expect(statisticCells(html, 'HP')).toEqual(['—', '73'])
    expect(statisticCells(html, 'Standing')).toEqual(['—', '#3'])
    expect(statisticCells(html, 'Board units')).toEqual(['—', '6'])
    expect(statisticCells(html, 'Placement')).toBeUndefined()
    expect(statisticCells(html, 'Level')).toBeUndefined()
    expect(statisticCells(html, 'Augments')).toBeUndefined()
    expect(html).toContain('Updated ')
    const lobby = render(teams, false, {game: 'Teamfight Tactics', phase: 'lobby'})
    expect(statisticCells(lobby, 'Standing')).toBeUndefined()
    expect(statisticCells(lobby, 'Board units')).toBeUndefined()
    expect(lobby).not.toContain('Updated ')
  })

  it('orders current TFT players by their standing and renders real optional counts including an empty board', () => {
    const html = render([{name: 'Players', players: [
      {name: 'Third#TEST', stats: {standing: 3, boardUnits: 6}},
      {name: 'First#TEST', stats: {standing: 1, boardUnits: 0, level: 4, augmentCount: 2}},
      {name: 'Second#TEST', stats: {standing: 2}},
    ]}], false, {game: 'Teamfight Tactics', phase: 'live', freeForAll: true})
    expect(cardNames(html)).toEqual(['First#TEST', 'Second#TEST', 'Third#TEST'])
    expect(statisticCells(html, 'Board units')).toEqual(['—', '0'])
    expect(statisticCells(html, 'Augments')).toEqual(['—', '2'])
    expect(statisticCells(html, 'Level')).toEqual(['—', '4'])
  })

  it.each(['lobby', 'matchmaking', 'readycheck', 'pregame'] as const)('keeps history but never presents old match data as %s statistics', phase => {
    const html = render([{name: 'Party', score: 13, won: true, players: [{
      ...player(0), self: true, leader: true, ready: true, role: 'middle',
      stats: {kills: 24, deaths: 12, assists: 4, roundKills: [3]}, score: '24 / 12 / 4',
    }]}], false, {phase})
    expect(statisticCells(html, 'Kills')).toEqual(['18'])
    expect(html).not.toMatch(/>Match<\//)
    expect(html).not.toContain('Tags earned this match')
    expect(html).not.toContain('24 / 12 / 4')
    expect(html).not.toContain('Victory')
    expect(html).toContain('Tags from past games')
    if (phase === 'readycheck') expect(html).not.toContain('Accepted')
    else expect(html).toContain('Ready')
    expect(html).toContain('Mid')
    if (phase !== 'pregame') {
      expect(html).toContain('Your party')
      expect(html).toContain('Leader')
    }
  })

  it.each(['League of Legends', 'Teamfight Tactics'] as const)('uses bundled %s ranks without requiring an agent portrait', game => {
    const html = render([{name: 'Party', players: [{name: 'Friend#EUW', riotId: 'Friend#EUW', currentRank: 'Gold III', peakRank: 'Emerald II', self: true}]}], false, {game, phase: 'lobby'})
    expect(html).toContain('Gold III rank emblem')
    expect(html).toContain('Emerald II rank emblem')
    expect(html).not.toContain('Agent unavailable')
    expect(html).not.toContain('Champion unavailable')
    expect(html).not.toContain('Statistics unavailable')
    expect(html).not.toContain('Level —')
  })

  it('renders TFT as a neutral field of players with a blue self card and only relevant stats', () => {
    const html = render([{name: 'Players', players: Array.from({length: 8}, (_, index) => ({
      name: `Tactician${index}#EUW`, riotId: `Tactician${index}#EUW`, self: index === 0,
      currentRank: 'Gold III', stats: {placement: index + 1, level: 9, gold: 30},
    }))}], false, {game: 'Teamfight Tactics', phase: 'live', freeForAll: true})
    expect(html.match(/pmc-card--ffa/g)).toHaveLength(7)
    expect(html.match(/pmc-card--self/g)).toHaveLength(1)
    expect(html).not.toContain('pmc-card--enemy')
    expect(html).not.toContain('Free for all')
    expect(html).not.toContain('Agent unavailable')
    expect(html).not.toContain('K/D')
    expect(statisticCells(html, 'Level')).toEqual(['—', '9'])
    expect(statisticCells(html, 'Placement')).toEqual(['—', '1'])
  })

  it('renders four confirmed Double Up pairs with a blue self card, green partner and six red opponents', () => {
    const teams: MatchTeam[] = Array.from({length: 4}, (_, duo) => ({name: `Duo ${duo + 1}`, grouping: 'duo', players: [
      {...player(duo * 2), self: duo === 2}, player(duo * 2 + 1),
    ]}))
    const html = render(teams, false, {game: 'Teamfight Tactics', phase: 'live', queueId: '1160', freeForAll: true})
    expect(html).toContain('data-layout="duos"')
    expect(html.match(/class="[^"]*pmc-team"/g)).toHaveLength(4)
    expect(html.match(/pmc-card--self/g)).toHaveLength(1)
    expect(html.match(/pmc-card--ally/g)).toHaveLength(1)
    expect(html.match(/pmc-card--enemy/g)).toHaveLength(6)
    expect(html).toContain('Your duo')
    expect(html).toContain('PARTNER')
    expect(html).not.toContain('Pairings unavailable')
    expect(html).not.toContain('pmc-card--ffa')
    expect(cardNames(html).slice(0, 2)).toEqual(['Player4#EU', 'Player5#EU'])
    expect(html.match(/position [12] of 2/g)).toHaveLength(8)
  })

  it('shows unassigned Double Up players neutrally instead of inventing allies or pairs', () => {
    const html = render([{name: 'Party', players: Array.from({length: 8}, (_, index) => ({...player(index), self: index === 0}))}], false, {game: 'Teamfight Tactics', phase: 'lobby', teamMode: 'duos'})
    expect(html).toContain('Pairings unavailable')
    expect(html).toContain('data-layout="duos"')
    expect(html.match(/pmc-card--neutral/g)).toHaveLength(7)
    expect(html.match(/pmc-card--self/g)).toHaveLength(1)
    expect(html).not.toContain('Your duo')
    expect(html).not.toContain('pmc-card--ally')
    expect(html).not.toContain('pmc-card--enemy')
    expect(html).not.toContain('draggable="true"')
  })

  it('keeps a known duo and remaining unknown players separate in a completed Double Up report', () => {
    const html = render([
      {name: 'Duo 1', grouping: 'duo', players: [{...player(0), self: true}, player(1)]},
      {name: 'Unassigned players', grouping: 'unassigned', players: [player(2), player(3)]},
    ], true, {game: 'Teamfight Tactics', mode: 'Double Up', freeForAll: true, allowReorder: true})
    expect(html).toContain('Your duo')
    expect(html).toContain('Pairings unavailable')
    expect(html.match(/pmc-card--ally/g)).toHaveLength(1)
    expect(html.match(/pmc-card--neutral/g)).toHaveLength(2)
    expect(html).not.toContain('draggable="true"')
    expect(html).not.toContain('pmc-card--enemy')
  })

  it('reserves a game-specific skeleton while League and TFT history is fetching', () => {
    const teams = [{name: 'Party', players: [{name: 'Friend#EUW', statsLoading: true}]}]
    const league = render(teams, false, {game: 'League of Legends', phase: 'lobby'})
    expect(statisticCells(league, 'CS')).toEqual(['Loading'])
    expect(statisticCells(league, 'Vision')).toEqual(['Loading'])
    expect(league).not.toMatch(/>ACS<\//)
    const tft = render(teams, false, {game: 'Teamfight Tactics', phase: 'lobby'})
    expect(statisticCells(tft, 'Placement')).toEqual(['Loading'])
    expect(tft).not.toMatch(/>K\/D<\//)
  })

  it.each([false, true])('follows explicit fetching, ready and unavailable states (completed=%s)', completed => {
    const subject = {...player(0), overallStats: undefined, statsLoading: true}
    const loading = render([{name: 'Blue', players: [subject]}], completed)
    expect(loading).toContain('Fetching stats')
    expect(loading).toContain('astryx-skeleton')
    expect(loading).not.toContain('astryx-spinner')
    for (const label of ['K/D', 'ACS', 'ADR', 'HS%', 'Kills', 'Deaths', 'Assists']) {
      expect(statisticCells(loading, label)?.[0]).toBe('Loading')
    }
    expect(loading).not.toMatch(/>Match</)
    expect(loading).toContain('aria-busy="true"')
    expect(loading).not.toContain('Statistics unavailable')

    const ready = render([{name: 'Blue', players: [{...subject, statsLoading: false, overallStats: player(0).overallStats}]}], completed)
    expect(ready).not.toContain('Fetching stats')
    expect(ready).not.toContain('astryx-skeleton')
    expect(ready).not.toContain('aria-busy="true"')
    expect(ready).toContain('Recent 5 games')
    expect(statisticCells(ready, 'Kills')).toEqual(['18'])

    const unavailable = render([{name: 'Blue', players: [{...subject, statsLoading: false}]}], completed)
    expect(unavailable).not.toContain('Fetching stats')
    expect(unavailable).not.toContain('astryx-skeleton')
    expect(unavailable).not.toContain('aria-busy="true"')
    expect(unavailable).toContain('Statistics unavailable')
  })

  it('retains available match statistics, ranks and tags while more statistics are fetching', () => {
    const html = render([{name: 'Blue', players: [{...player(0), statsLoading: true, stats: {kills: 3, deaths: 2, assists: 1, roundKills: [3], roundsPlayed: 1}}]}])
    expect(html).toContain('Fetching stats')
    expect(statisticCells(html, 'Kills')).toEqual(['18', '3'])
    expect(html).toContain('Tags from past games')
    expect(html).toContain('Tags earned this match')
    expect(html).toContain('Ascendant 2 rank emblem')
    expect(html).toContain('Immortal 1 rank emblem')
  })

  it('keeps the recorded match column visible while overall statistics are still fetching', () => {
    const html = render([{name: 'Blue', players: [{
      ...player(0), overallStats: undefined, statsLoading: true,
      stats: {kills: 24, deaths: 15, assists: 4, roundsPlayed: 22},
    }]}], true)
    expect(html).toContain('Fetching stats')
    expect(statisticCells(html, 'Kills')).toEqual(['Loading', '24'])
    expect(statisticCells(html, 'Deaths')).toEqual(['Loading', '15'])
    expect(statisticCells(html, 'Assists')).toEqual(['Loading', '4'])
    expect(html).not.toContain('Statistics unavailable')
  })

  it('does not infer fetching from absent statistics or display it for hidden players', () => {
    const html = render([{name: 'Blue', players: [
      {...player(0), overallStats: undefined},
      {...player(1), overallStats: undefined, statsLoading: true, hidden: true},
    ]}])
    expect(html).not.toContain('Fetching stats')
    expect(html).not.toContain('astryx-spinner')
    expect(html).not.toContain('astryx-skeleton')
    expect(html).not.toContain('aria-busy="true"')
    expect(html).not.toContain('Player1#EU')
    expect(html.match(/Statistics unavailable/g)).toHaveLength(2)
  })

  it('links a quiet fetching status to each busy card without parallel live announcements', () => {
    const html = render([{name: 'Blue', players: [0, 1, 2].map(index => ({...player(index), statsLoading: true}))}], true)
    const cards = [...html.matchAll(/<div\b[^>]*\bclass="[^"]*\bpmc-card\b[^"]*"[^>]*>/g)].map(([tag]) => tag)
    expect(cards).toHaveLength(3)
    const descriptions = cards.map(card => {
      expect(card).toContain('aria-busy="true"')
      return card.match(/aria-describedby="([^"]+)"/)?.[1]
    })
    expect(new Set(descriptions).size).toBe(3)
    for (const id of descriptions) {
      expect(id).toBeTruthy()
      expect(html).toMatch(new RegExp(`id="${id}"[^>]*role="status"[^>]*aria-live="off"`))
    }
    expect(html).not.toContain('pmc-card__fetching')
    expect(html).not.toContain('astryx-spinner')
  })

  it('keeps reports and inactive rosters read-only, including accidental reorder opt-in', () => {
    const teams = [{name: 'Blue', players: [player(0), player(1)]}]
    for (const html of [render(teams, true), render(teams, true, {allowReorder: true}), render(teams, false, {allowReorder: false})]) {
      expect(html).not.toContain('draggable="true"')
      expect(html).not.toContain('Reset order')
      expect(html).not.toContain('Escape cancels the move')
      expect(html).not.toContain('Reorder Player')
      expect(html).toContain('Player0#EU')
      expect(html).toContain('Player1#EU')
    }
  })
  it('places the own team first with four allies, one self and five opponents', () => {
    const own = Array.from({length: 5}, (_, index) => ({...player(index), self: index === 0}))
    const opponents = Array.from({length: 5}, (_, index) => player(index + 5))
    const html = render([{name: 'Red', players: opponents}, {name: 'Blue', players: own}])
    expect(html.indexOf('Player0#EU')).toBeLessThan(html.indexOf('Player5#EU'))
    expect(html.match(/pmc-card--self/g)).toHaveLength(1)
    expect(html.match(/pmc-card--ally/g)).toHaveLength(4)
    expect(html.match(/pmc-card--enemy/g)).toHaveLength(5)
    for (let index = 0; index < 10; index++) expect(html).toContain(`Player${index}#EU`)
  })

  it('renders opposing role matches in the same columns with accessible reorder controls', () => {
    const own = ['Omen', 'Cypher', 'Reyna', 'Sova', 'Jett'].map((agent, index) => ({...player(index), agent, self: index === 0}))
    const opponents = ['Fade', 'Raze', 'Killjoy', 'Phoenix', 'Brimstone'].map((agent, index) => ({...player(index + 10), agent}))
    const html = render([{name: 'Red', players: opponents}, {name: 'Blue', players: own}])
    expect(cardNames(html)).toEqual([4, 2, 3, 0, 1, 11, 13, 10, 14, 12].map(index => `Player${index}#EU`))
    expect(html.match(/draggable="true"/g)).toHaveLength(10)
    expect(html).toContain('Reorder Player4#EU, position 1 of 5')
    expect(html).toContain('Escape cancels the move')
    expect(html).toContain('Reset order')
  })

  it('combines Deathmatch buckets into one white roster and retains a blue self card', () => {
    const html = render([
      {name: 'Red', score: 4, players: [{...player(0), stats: {kills: 3}}, player(1)]},
      {name: 'Blue', score: 2, players: [{...player(2), self: true, stats: {kills: 8}}, player(3)]},
    ], false, {mode: 'Deathmatch'})
    expect(html.match(/pmc-card--ffa/g)).toHaveLength(3)
    expect(html.match(/pmc-card--self/g)).toHaveLength(1)
    expect(html).not.toContain('pmc-card--enemy')
    expect(html).not.toContain('Your team')
    expect(cardNames(html)[0]).toBe('Player2#EU')
    expect(html).not.toContain('pmc-team__score')
  })

  it('keeps every Gauntlet team and uneven roster without forcing five-player ordering', () => {
    const groups = Array.from({length: 8}, (_, team) => ({name: `Duo ${team + 1}`, players: [
      {...player(team * 2), agent: 'Omen', self: team === 0}, {...player(team * 2 + 1), agent: 'Jett'},
    ]}))
    const gauntlet = render(groups, false, {mode: 'Gauntlet: Glitched'})
    expect(cardNames(gauntlet)).toEqual(Array.from({length: 16}, (_, index) => `Player${index}#EU`))
    expect(gauntlet).toContain('Duo 8')
    const asymmetric = render([
      {name: 'Blue', players: [{...player(0), agent: 'Omen', self: true}, {...player(1), agent: 'Jett'}]},
      {name: 'Red', players: [{...player(2), agent: 'Jett'}, {...player(3), agent: 'Cypher'}, {...player(4), agent: 'Omen'}]},
    ])
    expect(cardNames(asymmetric)).toEqual([0, 1, 2, 3, 4].map(index => `Player${index}#EU`))
  })

  it('does not invent live statistics and keeps recent evidence labeled', () => {
    const html = render([{name: 'Blue', players: [{...player(0), self: true}]}])
    expect(html).toContain('Overall')
    expect(html).toContain('Recent 5 games')
    expect(html).not.toMatch(/>Match</)
    expect(html).toContain('Certified problem')
    expect(html).not.toContain('Tags earned this match')
    expect(html).toContain('V26:A1')
    expect(html).toContain('Level 200')
  })

  it('adds a separate match column and earned tags only from actual match evidence', () => {
    const html = render([{name: 'Blue', players: [{...player(0), self: true, stats: {kills: 3, deaths: 2, assists: 1, roundKills: [3], roundsPlayed: 1}}]}])
    expect(html).toMatch(/>Match</)
    expect(html).toMatch(/Three(?:&#x27;|')s a crowd/)
    expect(html).toContain('Tags from past games')
    expect(html).toContain('Tags earned this match')
  })

  it('keeps every history and match explanation available through a native keyboard button', () => {
    const subject = {...player(0), self: true, stats: {kills: 3, deaths: 2, assists: 1, roundKills: [3], roundsPlayed: 1}}
    const html = render([{name: 'Blue', players: [subject]}])
    const buttonLabels = [...html.matchAll(/<button\b[^>]*>([\s\S]*?)<\/button>/g)]
      .map(([, content]) => content.replace(/<[^>]+>/g, ''))
    const tags = [...historicalPerformanceTags(subject, 'VALORANT'), ...playerPerformanceTags(subject, 'VALORANT')]

    expect(tags.length).toBeGreaterThan(1)
    for (const tag of tags) {
      expect(buttonLabels).toContain(renderToStaticMarkup(<>{tag.label}</>))
      expect(html).toContain(`aria-description="${renderToStaticMarkup(<>{tag.detail}</>)}"`)
    }
  })

  it('only marks real grouped parties and never prints the grouping identifier', () => {
    const html = render([{name: 'Blue', players: [
      {...player(0), partyId: 'opaque-group-a'}, {...player(1), partyId: 'opaque-group-a'},
      {...player(2), partyId: 'opaque-solo'},
    ]}])
    expect(html.match(/data-party="yellow"/g)).toHaveLength(2)
    expect(html).not.toContain('opaque-group-a')
    expect(html).not.toContain('opaque-solo')
  })

  it('keeps raw match Score and Damage when only the overall source has a round count', () => {
    const html = render([{name: 'Blue', players: [{
      ...player(0), self: true,
      overallStats: {matchesPlayed: 5, combatScore: 24000, damage: 15000, roundsPlayed: 100},
      stats: {combatScore: 900, damage: 600},
    }]}], true)

    expect(statisticCells(html, 'ACS')).toEqual(['240', '—'])
    expect(statisticCells(html, 'ADR')).toEqual(['150', '—'])
    expect(statisticCells(html, 'Score')?.[1]).toBe('900')
    expect(statisticCells(html, 'Damage')?.[1]).toBe('600')
  })

  it('keeps overall Score and Damage averages when only the match source has a round count', () => {
    const html = render([{name: 'Blue', players: [{
      ...player(0), self: true,
      overallStats: {matchesPlayed: 5, combatScore: 2000, damage: 1000},
      stats: {combatScore: 6000, damage: 4000, roundsPlayed: 20},
    }]}], true)

    expect(statisticCells(html, 'ACS')).toEqual(['—', '300'])
    expect(statisticCells(html, 'ADR')).toEqual(['—', '200'])
    expect(statisticCells(html, 'Score')?.[0]).toBe('400')
    expect(statisticCells(html, 'Damage')?.[0]).toBe('200')
  })

  it('distinguishes verified current rank from rank recorded in a completed match', () => {
    const known = render([{name: 'Blue', players: [{...player(0), self: true, rank: 'Diamond 1'}]}], true)
    expect(known).toContain('Ascendant 2 rank emblem')
    expect(known).toMatch(/>Current<\//)
    expect(known).not.toMatch(/>Match rank<\//)

    const historical = render([{name: 'Blue', players: [{...player(0), self: true, currentRank: undefined, rank: 'Diamond 1'}]}], true)
    expect(historical).toContain('Diamond 1 rank emblem')
    expect(historical).toMatch(/>Match rank<\//)
    expect(historical).not.toMatch(/>Current<\//)
  })

  it('places readable rank names and current or season captions after the rank image', () => {
    const html = render([{name: 'Blue', players: [{...player(0), self: true}]}])
    const currentImage = html.indexOf('alt="Ascendant 2 rank emblem"')
    const currentCaption = html.indexOf('>Current</')
    const peakImage = html.indexOf('alt="Immortal 1 rank emblem"')
    const seasonCaption = html.indexOf('>V26:A1</')

    expect(currentImage).toBeGreaterThan(-1)
    expect(currentCaption).toBeGreaterThan(currentImage)
    expect(html.indexOf('>Ascendant 2</')).toBeGreaterThan(currentImage)
    expect(peakImage).toBeGreaterThan(-1)
    expect(seasonCaption).toBeGreaterThan(peakImage)
    expect(html.indexOf('>Immortal 1</')).toBeGreaterThan(peakImage)
  })
})
