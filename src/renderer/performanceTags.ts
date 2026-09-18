import {t} from './i18n'
import type {PlayerStats} from './types'

export interface PerformanceTag {
  label: string
  detail: string
}

interface TagWindow {
  context: 'match' | 'history'
  expectedMatches: number
  /** Historical totals already collected into one PlayerStats object. */
  aggregatedMatches?: number
}

type TagCategory = 'rounds' | 'aim' | 'impact' | 'support' | 'weapon' | 'form'
interface Candidate extends PerformanceTag {
  category: TagCategory
  priority: number
}

export const isStatCount = (value: unknown): value is number => typeof value === 'number'
  && Number.isInteger(value) && value >= 0 && value <= 100_000_000

export function hasValidWeaponEvents(stats: PlayerStats): boolean {
  return Array.isArray(stats.weaponUsage) && stats.weaponUsage.length <= 32
    && stats.weaponUsage.every(entry => entry && typeof entry.weapon === 'string'
      && entry.weapon.trim().length > 0 && entry.weapon.length <= 80
      && !Array.from(entry.weapon).some(character => character.charCodeAt(0) < 32 || character.charCodeAt(0) === 127)
      && isStatCount(entry.kills))
    && (stats.kills === undefined || (isStatCount(stats.kills)
      && stats.weaponUsage.reduce((sum, entry) => sum + entry.kills, 0) <= stats.kills))
}

export function hasValidRoundEvents(stats: PlayerStats): boolean {
  const eventRounds = stats.roundsAnalyzed ?? stats.roundsPlayed
  return Array.isArray(stats.roundKills) && stats.roundKills.length > 0 && stats.roundKills.length <= 128
    && stats.roundKills.every(kills => isStatCount(kills) && kills <= 64)
    && (eventRounds === undefined || (isStatCount(eventRounds)
      && eventRounds === stats.roundKills.length))
    && (stats.roundsAnalyzed === undefined || stats.roundsPlayed === undefined
      || (isStatCount(stats.roundsPlayed) && stats.roundsPlayed >= stats.roundsAnalyzed
        && stats.roundsPlayed <= stats.roundsAnalyzed + 1))
    && (stats.kills === undefined || (isStatCount(stats.kills)
      && stats.roundKills.reduce((sum, kills) => sum + kills, 0) === stats.kills))
}

const weaponLabels: Record<string, string> = {
  vandal: 'Vandal loyalist',
  phantom: 'Phantom loyalist',
  operator: 'Operator landlord',
  marshal: 'Marshal artist',
  outlaw: 'Outlaw behavior',
  sheriff: "Sheriff's office",
  judge: 'Judge & jury',
  bucky: 'Bucky business',
  odin: 'Odin enjoyer',
  ares: 'Spray department',
  ghost: 'Ghost writer',
  classic: 'Default menace',
  shorty: 'Shorty business',
  stinger: 'Stinger operation',
  spectre: 'Spectre specialist',
  guardian: 'Guardian angel',
  bulldog: 'Bulldog believer',
  frenzy: 'Frenzy enjoyer',
}

/** Five poor games must be individually observed, never inferred from a low average. */
function walkingOrbEvidence(stats: PlayerStats): Array<{kills: number; deaths: number}> | undefined {
  const games = stats.recentKda
  if (stats.matchesPlayed !== 5 || !Array.isArray(games) || games.length !== 5
    || !games.every(game => game && isStatCount(game.kills) && isStatCount(game.deaths)
      && game.deaths >= 10 && game.kills / game.deaths <= 0.6)) return undefined
  const kills = games.reduce((sum, game) => sum + game.kills, 0)
  const deaths = games.reduce((sum, game) => sum + game.deaths, 0)
  if ((stats.kills !== undefined && (!isStatCount(stats.kills) || stats.kills !== kills))
    || (stats.deaths !== undefined && (!isStatCount(stats.deaths) || stats.deaths !== deaths))) return undefined
  return games
}

/**
 * A deterministic, deliberately small set of observations, not personality labels.
 * No entry, clutch, accuracy, AFK, smurf or cheating claims can be made from this data.
 * Every ratio requires its own complete denominator; absent fields never become zero.
 */
export function selectPerformanceTags(stats: PlayerStats[], window: TagWindow): PerformanceTag[] {
  const history = window.context === 'history'
  const sample = window.aggregatedMatches ?? stats.length
  if (stats.length === 0 || !isStatCount(sample) || sample < 1 || sample > 100
    || (history && sample < 3)) return []

  const complete = stats.length === window.expectedMatches
  const candidates: Candidate[] = []
  const add = (category: TagCategory, priority: number, label: string, detail: string) => {
    candidates.push({category, priority, label, detail: history ? t('{{detail}} Across {{count}} recent games.', {detail, count: sample}) : detail})
  }
  const total = (key: 'kills' | 'deaths' | 'assists' | 'roundsPlayed' | 'combatScore' | 'damage') => {
    if (!complete || !stats.every(item => isStatCount(item[key]))) return undefined
    return stats.reduce((sum, item) => sum + (item[key] as number), 0)
  }
  const kills = total('kills')
  const deaths = total('deaths')
  const assists = total('assists')
  const rounds = total('roundsPlayed')
  const score = total('combatScore')
  const damage = total('damage')
  const enoughRounds = rounds !== undefined && rounds >= (history ? 36 : 12)

  const walkingOrbGames = history && complete && window.aggregatedMatches === 5 && stats.length === 1
    ? walkingOrbEvidence(stats[0]) : undefined
  if (walkingOrbGames) {
    const ratios = walkingOrbGames.map(game => `${(game.kills / game.deaths).toFixed(2)} (${game.kills}/${game.deaths})`).join(', ')
    add('impact', 120, 'walking orb 🥀',
      t("Five games, five donations. At this point you’re the enemy team’s ult subscription. Last five K/Ds, newest first: {{ratios}}. Every game: ≤0.60 K/D and ≥10 deaths.", {ratios: ratios}))
  }

  // Choose the strongest observed multikill. Total kills alone can never earn one.
  const multikills = [0, 0, 0, 0]
  for (const item of stats) {
    if (!hasValidRoundEvents(item)) continue
    for (const count of item.roundKills ?? []) {
      if (count >= 2) multikills[Math.min(count, 5) - 2] += 1
    }
  }
  const moments = ['Two-for-one', "Three's a crowd", 'Four-piece combo', 'Lobby eviction']
  for (let index = multikills.length - 1; index >= 0; index--) {
    const count = multikills[index]
    if (!count) continue
    add('rounds', 100 + index, moments[index], t('{{count}} recorded rounds with {{eliminations}} eliminations.', {count, eliminations: `${index + 2}${index === 3 ? '+' : ''}`}))
    break
  }

  // Landed-hit share is not shot accuracy. All three hit locations must be present.
  if (complete && stats.every(item => [item.headshots, item.bodyshots, item.legshots].every(isStatCount))) {
    const head = stats.reduce((sum, item) => sum + item.headshots!, 0)
    const body = stats.reduce((sum, item) => sum + item.bodyshots!, 0)
    const legs = stats.reduce((sum, item) => sum + item.legshots!, 0)
    const hits = head + body + legs
    if (hits >= (history ? 90 : 30)) {
      if (head / hits >= 0.3) {
        add('aim', 90, 'Headshot merchant', t("{{value1}}% head hits ({{head}} of {{hits}} landed hits).", {value1: Math.round(head / hits * 100), head: head, hits: hits}))
      } else if (head / hits <= 0.08 && body / hits >= 0.8) {
        add('aim', 65, 'Center-mass enjoyer', t("{{value1}}% body hits and {{value2}}% head hits across {{hits}} landed hits.", {value1: Math.round(body / hits * 100), value2: Math.round(head / hits * 100), hits: hits}))
      }
    }
  }

  if (enoughRounds && rounds !== undefined) {
    if (assists !== undefined && assists >= (history ? 24 : 8) && assists / rounds >= 0.6) {
      add('support', 86, 'Assist department', t("{{assists}} assists in {{rounds}} rounds ({{value3}} per round).", {assists: assists, rounds: rounds, value3: (assists / rounds).toFixed(2)}))
    }
    if (kills !== undefined && deaths !== undefined && kills >= (history ? 36 : 12)
      && kills / Math.max(deaths, 1) >= 1.5) {
      add('impact', 82, 'Certified problem', deaths > 0 ? t("{{value1}} K/D ({{kills}} kills, {{deaths}} deaths) over {{rounds}} rounds.", {value1: (kills / deaths).toFixed(2), kills: kills, deaths: deaths, rounds: rounds}) : t("{{kills}} kills without a recorded death over {{rounds}} rounds.", {kills: kills, rounds: rounds}))
    }
    if (score !== undefined && score / rounds >= 280) {
      add('impact', 81, 'Lobby landlord', t("{{value1}} average combat score over {{rounds}} rounds.", {value1: Math.round(score / rounds), rounds: rounds}))
    }
    if (damage !== undefined && damage / rounds >= 170) {
      add('impact', 80, 'Health inspector', t("{{value1}} damage per round across {{rounds}} rounds.", {value1: Math.round(damage / rounds), rounds: rounds}))
    }
    if (kills !== undefined && assists !== undefined) {
      if (deaths !== undefined && deaths >= (history ? 36 : 12) && deaths / rounds >= 0.85
        && kills / deaths <= 0.6 && (kills + assists) / rounds < 0.65) {
        add('impact', 55, "Death's bestie", t("{{kills}} kills, {{deaths}} deaths and {{assists}} assists in {{rounds}} rounds ({{value5}} deaths per round).", {kills: kills, deaths: deaths, assists: assists, rounds: rounds, value5: (deaths / rounds).toFixed(2)}))
      } else if ((kills + assists) / rounds < 0.5) {
        add('impact', 50, 'Rough shift', t('{{kills}} and {{assists}} across {{rounds}} rounds ({{average}} combined per round).', {kills: t('{{count}} kills', {count: kills}), assists: t('{{count}} assists', {count: assists}), rounds, average: ((kills + assists) / rounds).toFixed(2)}))
      }
    }
  }

  if (complete && kills !== undefined && kills >= (history ? 24 : 8)
    && stats.every(hasValidWeaponEvents)) {
    const weapons = new Map<string, {name: string; kills: number}>()
    for (const item of stats) {
      for (const weapon of item.weaponUsage ?? []) {
        const key = weapon.weapon.trim().toLocaleLowerCase()
        const previous = weapons.get(key)
        weapons.set(key, {name: previous?.name ?? weapon.weapon.trim(), kills: (previous?.kills ?? 0) + weapon.kills})
      }
    }
    const favorite = [...weapons.entries()].sort((left, right) => right[1].kills - left[1].kills || left[0].localeCompare(right[0]))[0]
    if (favorite && favorite[1].kills / kills >= 0.6 && weaponLabels[favorite[0]]) {
      add('weapon', 84, weaponLabels[favorite[0]], t("{{value1}} of {{kills}} eliminations used the {{value3}} ({{value4}}%).", {value1: favorite[1].kills, kills: kills, value3: favorite[1].name, value4: Math.round(favorite[1].kills / kills * 100)}))
    }
  }

  // Wins are an aggregate fact, never evidence of a consecutive streak.
  const wins = window.aggregatedMatches !== undefined && stats.length === 1 ? stats[0].wins : undefined
  if (history && sample >= 5 && isStatCount(wins) && wins <= sample) {
    if (wins / sample >= 0.6) add('form', 70, 'Win collector', t("{{wins}} wins ({{value2}}% win rate).", {wins: wins, value2: Math.round(wins / sample * 100)}))
    else if (wins / sample <= 0.2) add('form', 45, 'Queueing through it', t('{{count}} wins ({{percentage}}% win rate).', {count: wins, percentage: Math.round(wins / sample * 100)}))
  }

  const categories = new Set<TagCategory>()
  return candidates.sort((left, right) => right.priority - left.priority || left.label.localeCompare(right.label))
    .filter(candidate => {
      if (categories.has(candidate.category)) return false
      categories.add(candidate.category)
      return true
    }).slice(0, 3).map(({label, detail}) => ({label: t(label), detail}))
}
