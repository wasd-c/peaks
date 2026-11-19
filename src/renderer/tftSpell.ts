import type {TftCalculation, TftChampion, TftScaling} from './tftCatalog'

export type TftSpellPart =
  | {kind: 'text'; text: string; emphasis?: boolean; scaling?: TftScaling}
  | {kind: 'break'}
  | {kind: 'icon'; scaling: TftScaling}
  | {kind: 'value'; values: Array<number | null>; scaling?: TftScaling}
  | {kind: 'unavailable'; reason?: 'live' | 'missing'}

const scalingNames: Record<string, TftScaling> = {
  scaleap: 'ap', scalead: 'ad', scalehealth: 'health', scalehp: 'health',
  scalearmor: 'armor', scalemr: 'mr', scalemagicresist: 'mr', scaleas: 'speed', scalemana: 'mana',
  magicdamage: 'ap', physicaldamage: 'ad', healing: 'health', shield: 'health',
}
const binHash = (name: string) => {
  let hash = 2166136261
  for (const char of name.toLowerCase()) hash = Math.imul(hash ^ char.charCodeAt(0), 16777619) >>> 0
  return `{${hash.toString(16).padStart(8, '0')}}`
}
const lookup = <T,>(source: Record<string, T>, name: string): T | undefined =>
  (Object.hasOwn(source, name) ? source[name] : undefined) ?? source[binHash(name)] ?? Object.entries(source).find(([key]) => key.toLowerCase() === name.toLowerCase() || binHash(key) === name.toLowerCase())?.[1]

const knownTypes = ['NamedDataValueCalculationPart', 'NumberCalculationPart', 'SumOfSubPartsCalculationPart',
  'ProductOfSubPartsCalculationPart', 'GameCalculation', 'SubPartScaledProportionalToStat', 'GameCalculationModified',
  'StatByNamedDataValueCalculationPart', 'StatBySubPartCalculationPart', 'StatByCoefficientCalculationPart',
  'ExponentSubPartsCalculationPart', 'ClampSubPartsCalculationPart', 'MinOfSubPartsCalculationPart', 'MaxOfSubPartsCalculationPart']
const typeNames = Object.fromEntries(knownTypes.map(name => [binHash(name), name]))
const nodeType = (part: TftCalculation) => typeNames[part.__type ?? ''] ?? part.__type
const finite = (value: unknown): number | null => typeof value === 'number' && Number.isFinite(value) ? value : null
const rounded = (value: number | null) => value != null && Number.isFinite(value) ? Math.round(value * 100) / 100 : null
const expressionParts = (expression: string) => /^([\w.{}]+)(?:\s*([*/])\s*(-?\d+(?:\.\d+)?))?(%)?$/.exec(expression)

/** Curvetable exports use named stats and zero-based star arrays. Translate
 * only their explicit terms for presentation; resolved baseline values remain
 * the authoritative numeric fallback for operations we cannot decompose.
 */
function curveFormula(calculation: TftCalculation): TftCalculation | undefined {
  if (!Array.isArray(calculation.terms) || !calculation.terms.length) return undefined
  let result: TftCalculation | undefined
  for (const raw of calculation.terms) {
    if (!raw || typeof raw !== 'object') return undefined
    const term = raw as TftCalculation
    // These additional operations are not a plain stat coefficient. Keep the
    // provider's resolved values instead of guessing how to split them.
    if (term.preAdd || term.postAddRow) return undefined
    const coefficient: TftCalculation = {__type: 'CurveValueCalculationPart', values: term.coefficient}
    let node: TftCalculation
    if (term.type === 'flat') node = {__type: 'CurveValueCalculationPart', values: term.values}
    else if (term.type === 'scaled') {
      if (term.scaling === 'AbilityPower' || term.scaling === 'AttackDamage') {
        node = {__type: 'SubPartScaledProportionalToStat', mSubpart: coefficient,
          mRatio: term.scaling === 'AbilityPower' ? 0.01 : 1, mStat: term.scaling === 'AbilityPower' ? 0 : 3,
          mStyleTagIfScaled: term.scaling === 'AbilityPower' ? 'scaleAP' : 'scaleAD'}
      } else if (['HealthMax', 'Armor', 'MagicResist', 'BasicAttackDamage'].includes(String(term.scaling))) {
        const stats: Record<string, [number, string]> = {HealthMax: [12, 'scaleHealth'], Armor: [1, 'scaleArmor'],
          MagicResist: [6, 'scaleMR'], BasicAttackDamage: [2, 'scaleAD']}
        const [mStat, mStyleTagIfScaled] = stats[String(term.scaling)]
        node = {__type: 'StatBySubPartCalculationPart', mSubpart: coefficient, mStat, mStyleTagIfScaled}
      } else if (/^[A-Za-z]+Calc\d+$/.test(String(term.scaling))) {
        node = {__type: 'ProductOfSubPartsCalculationPart', mPart1: coefficient,
          mPart2: {mSpellCalculationKey: `TFTCalculationAttributes.${term.scaling}`}}
      } else return undefined
    } else return undefined
    switch (term.op) {
      case 'override': result = node; break
      case 'add': result = result ? {__type: 'SumOfSubPartsCalculationPart', mSubparts: [result, node]} : node; break
      case 'multiply': case 'divide':
        if (!result) return undefined
        result = {__type: 'ProductOfSubPartsCalculationPart', mPart1: result, mPart2: term.op === 'multiply' ? node
          : {__type: 'ExponentSubPartsCalculationPart', part1: node, part2: {__type: 'NumberCalculationPart', mNumber: -1}}}
        break
      default: return undefined
    }
  }
  return result
}

function spellEvaluator(champion: TftChampion, star: number) {
  const {variables, calculations} = champion.ability
  const named = (name: string): number | null => finite(lookup(variables, name)?.[star])
  const calculate = (part: TftCalculation | undefined, seen: string[] = [], depth = 0): number | null => {
    if (!part || seen.length > 16 || depth > 32) return null
    const child = (key: string) => calculate(part[key] as TftCalculation | undefined, seen, depth + 1)
    const children = (parts: unknown): number[] | null => {
      if (!Array.isArray(parts) || !parts.length) return null
      const values = parts.map(p => calculate(p as TftCalculation, seen, depth + 1))
      return values.some(value => value == null) ? null : values as number[]
    }
    const combine = (parts: unknown, multiply = false): number | null =>
      children(parts)?.reduce((a, b) => multiply ? a * b : a + b, multiply ? 1 : 0) ?? null
    switch (nodeType(part)) {
      case 'NamedDataValueCalculationPart': return named(String(part.mDataValue))
      case 'CurveValueCalculationPart': return Array.isArray(part.values) ? finite(part.values[star - 1]) : null
      case 'GameCalculationCurveTable': return part.resolved === true && Array.isArray(part.values) ? finite(part.values[star - 1]) : null
      // Riot omits zero-valued scalar fields from BIN JSON.
      case 'NumberCalculationPart': return finite(part.mNumber === undefined ? 0 : part.mNumber)
      case 'SumOfSubPartsCalculationPart': return combine(part.mSubparts)
      case 'ProductOfSubPartsCalculationPart': return combine([part.mPart1, part.mPart2], true)
      case 'ExponentSubPartsCalculationPart': {
        const base = child('part1'), exponent = child('part2')
        return base != null && exponent != null ? finite(Math.pow(base, exponent)) : null
      }
      case 'MinOfSubPartsCalculationPart': case 'MaxOfSubPartsCalculationPart': {
        const values = children(part.mSubparts)
        return values ? (nodeType(part) === 'MinOfSubPartsCalculationPart' ? Math.min(...values) : Math.max(...values)) : null
      }
      case 'ClampSubPartsCalculationPart': {
        const value = combine(part.mSubparts)
        return value == null ? null : Math.min(finite(part.mCeiling) ?? Infinity, Math.max(finite(part.mFloor) ?? -Infinity, value))
      }
      case 'GameCalculation': {
        const value = combine(part.mFormulaParts)
        const multiplier = part.mMultiplier ? child('mMultiplier') : 1
        return value != null && multiplier != null ? value * multiplier * (part.mDisplayAsPercent ? 100 : 1) : null
      }
      case 'SubPartScaledProportionalToStat': {
        const value = child('mSubpart'), ratio = finite(part.mRatio)
        // The existing catalog uses AP=100 and the modern TFT AD multiplier=1.
        // Do not replace missing current AD/health with a one-star base stat.
        const baseline = !part.mStat ? 100 : part.mStat === 3 ? 1 : null
        if (part.mStatFormula || part['{94fb4b0c}']) return null
        return value != null && ratio != null && baseline != null ? value * ratio * baseline : null
      }
      case 'GameCalculationModified': {
        if (part.mOverrideSpellLevel != null) return null
        const value = resolve(String(part.mModifiedGameCalculation), seen)
        const multiplier = part.mMultiplier ? child('mMultiplier') : 1
        return value != null && multiplier != null ? value * multiplier : null
      }
      default:
        // Riot's reference node has a hashed type in some patches.
        return typeof part.mSpellCalculationKey === 'string' ? resolve(part.mSpellCalculationKey, seen) : null
    }
  }
  const resolve = (name: string, seen: string[] = []): number | null => {
    if (seen.includes(name.toLowerCase())) return null
    return named(name) ?? calculate(lookup(calculations, name), [...seen, name.toLowerCase()])
  }
  return {named, calculate, resolve}
}

/** Evaluate only supported, explicit Riot formulas at their unmodified baseline.
 * No guessing from Modified prefixes and no eval of provider text.
 */
export function spellValue(champion: TftChampion, expression: string, star: number): number | null {
  if (!Number.isInteger(star) || star < 1 || star > 4) return null
  const match = expressionParts(expression)
  if (!match) return null
  const base = spellEvaluator(champion, star).resolve(match[1])
  if (base == null) return null
  const operand = match[3] == null ? 1 : Number(match[3])
  const result = match[2] === '/' ? base / operand : base * operand
  return rounded(result)
}

type FormulaTerm = {values: Array<number | null>; scaling?: TftScaling; percent?: boolean}

/** Preserve stat coefficients when actual combat AD/health are unavailable.
 * Their meaning comes from Riot's stat tags at this placeholder, never from the
 * champion's name or a guessed star-stat growth curve.
 */
function formulaTerms(champion: TftChampion, expression: string, hints: TftScaling[]): FormulaTerm[] | null {
  const match = expressionParts(expression)
  if (!match) return null
  const evaluators = [1, 2, 3, 4].map(star => spellEvaluator(champion, star))
  const values = (part: TftCalculation) => evaluators.map(evaluator => evaluator.calculate(part))
  const multiply = (terms: FormulaTerm[], factors: Array<number | null>) => terms.map(term => ({...term,
    values: term.values.map((value, i) => value != null && factors[i] != null ? rounded(value * factors[i]!) : null)}))
  const statScaling = (part: TftCalculation): TftScaling | undefined => {
    const tag = scalingNames[String(part.mStyleTagIfScaled ?? part.mStyleTag ?? '').toLowerCase()]
    if (tag) return tag
    if (!part.mStat) return 'ap'
    if (part.mStat === 1) return 'armor'
    if (part.mStat === 2) return 'ad'
    // Stat IDs after AD moved when Riot inserted the AD multiplier. Require
    // the tooltip's own icon to disambiguate historical/current spell nodes.
    if ((part.mStat === 11 || part.mStat === 12) && hints.includes('health')) return 'health'
    if ((part.mStat === 5 || part.mStat === 6) && hints.includes('mr')) return 'mr'
    if ((part.mStat === 3 || part.mStat === 4) && hints.includes('speed')) return 'speed'
    if (part.mStat === 3 && hints.includes('ad')) return 'ad'
    return undefined
  }
  const flatten = (part: TftCalculation | undefined, seen: string[] = [], depth = 0): FormulaTerm[] | null => {
    if (!part || depth > 32 || seen.length > 16) return null
    const reference = (name: string): FormulaTerm[] | null => {
      if (seen.includes(name.toLowerCase())) return null
      return flatten(lookup(champion.ability.calculations, name), [...seen, name.toLowerCase()], depth + 1)
    }
    const sum = (parts: unknown): FormulaTerm[] | null => {
      if (!Array.isArray(parts) || !parts.length) return null
      const terms = parts.map(child => flatten(child as TftCalculation, seen, depth + 1))
      return terms.some(term => term == null) ? null : terms.flat() as FormulaTerm[]
    }
    const kind = nodeType(part)
    if (typeof part.mSpellCalculationKey === 'string') return reference(part.mSpellCalculationKey)
    if (kind === 'GameCalculationCurveTable') {
      const formula = curveFormula(part)
      return formula ? flatten(formula, seen, depth + 1) : null
    }
    if (kind === 'GameCalculationModified') {
      if (part.mOverrideSpellLevel != null) return null
      const terms = reference(String(part.mModifiedGameCalculation))
      return terms && part.mMultiplier ? multiply(terms, values(part.mMultiplier as TftCalculation)) : terms
    }
    if (kind === 'GameCalculation' || kind === 'SumOfSubPartsCalculationPart') {
      const terms = sum(kind === 'GameCalculation' ? part.mFormulaParts : part.mSubparts)
      if (!terms) return null
      const factors = part.mMultiplier ? values(part.mMultiplier as TftCalculation) : [1, 1, 1, 1]
      return multiply(terms, factors.map(value => value == null ? null : value * (part.mDisplayAsPercent ? 100 : 1)))
    }
    if (kind === 'ProductOfSubPartsCalculationPart') {
      const first = flatten(part.mPart1 as TftCalculation, seen, depth + 1)
      const second = flatten(part.mPart2 as TftCalculation, seen, depth + 1)
      const scalar = (terms: FormulaTerm[] | null) => terms?.every(term => !term.scaling && !term.percent)
      if (first && scalar(second)) return multiply(first, values(part.mPart2 as TftCalculation))
      if (second && scalar(first)) return multiply(second, values(part.mPart1 as TftCalculation))
    }
    if (['StatByNamedDataValueCalculationPart', 'StatByCoefficientCalculationPart', 'StatBySubPartCalculationPart', 'SubPartScaledProportionalToStat'].includes(kind ?? '')) {
      const scaling = statScaling(part)
      if (!scaling || part.mStatFormula || part['{94fb4b0c}']) return null
      const calculated = values(part)
      if (kind === 'SubPartScaledProportionalToStat' && (scaling === 'ap' || scaling === 'ad')
        && calculated.slice(0, 3).every(value => value != null)) return [{values: calculated, scaling}]
      const coefficient = kind === 'StatByNamedDataValueCalculationPart'
        ? evaluators.map(evaluator => evaluator.named(String(part.mDataValue)))
        : kind === 'StatByCoefficientCalculationPart' ? [1, 2, 3, 4].map(() => finite(part.mCoefficient))
          : values(part.mSubpart as TftCalculation)
      const ratio = kind === 'SubPartScaledProportionalToStat' ? finite(part.mRatio) : 1
      if (ratio == null) return null
      return [{values: coefficient.map(value => value == null ? null : rounded(value * ratio * 100)), scaling, percent: true}]
    }
    const calculated = values(part)
    return calculated.slice(0, 3).some(value => value == null) ? null : [{values: calculated}]
  }
  const terms = flatten(lookup(champion.ability.calculations, match[1]), [match[1].toLowerCase()])
  if (!terms) return null
  const operand = match[3] == null ? 1 : Number(match[3])
  return multiply(terms, [1, 2, 3, 4].map(() => match[2] === '/' ? 1 / operand : operand))
}

function isLiveValue(champion: TftChampion, expression: string): boolean {
  if (/^TFTUnitProperty[.:]|^TFTSpellAttributes\./i.test(expression)
    || /^Stack$/i.test(expression) && !lookup(champion.ability.variables, expression)) return true
  const seen = new Set<string>()
  const inspect = (part: unknown, depth = 0): boolean => {
    if (!part || typeof part !== 'object' || depth > 32) return false
    const value = part as TftCalculation
    if (String(value.__type).startsWith('BuffCounter') || value.mStatFormula || value['{94fb4b0c}']
      || value.type === 'runtime' || value.type === 'scaled' && ['Stack', 'Health', 'OutgoingDamageMultiplier'].includes(String(value.scaling))) return true
    const references = [value.mSpellCalculationKey, value.mModifiedGameCalculation]
    if (value.type === 'scaled' && /^[A-Za-z]+Calc\d+$/.test(String(value.scaling))) references.push(`TFTCalculationAttributes.${value.scaling}`)
    for (const name of references) {
      if (typeof name === 'string' && !seen.has(name)) {
        seen.add(name)
        if (inspect(lookup(champion.ability.calculations, name), depth + 1)) return true
      }
    }
    return Object.values(value).some(child => typeof child === 'object' && inspect(child, depth + 1))
  }
  return inspect(lookup(champion.ability.calculations, expressionParts(expression)?.[1] ?? expression))
}

function decode(text: string): string {
  const entities: Record<string, string> = {nbsp: ' ', amp: '&', lt: '<', gt: '>', quot: '"', apos: "'"}
  return text.replace(/&(#x[\da-f]+|#\d+|\w+);/gi, (match, entity: string) => {
    if (!entity.startsWith('#')) return entities[entity] ?? match
    const point = entity[1].toLowerCase() === 'x' ? parseInt(entity.slice(2), 16) : Number(entity.slice(1))
    return point > 0 && point <= 0x10ffff ? String.fromCodePoint(point) : ''
  })
}

/** Parse a small allowlist into React text, never inject Riot markup as HTML. */
export function tftSpellParts(champion: TftChampion, language: string): TftSpellPart[] {
  const description = champion.ability.descriptions[language] || champion.ability.descriptions.en || ''
  const parts: TftSpellPart[] = []
  const stack: Array<{name: string; hidden: boolean}> = []
  const tokens = description.replace(/\r?\\n|\r\n?/g, '\n').split(/(<[^>]*>|@[^@]+@|%i:[^%]+%|\{\{[^}]+\}\}|\n)/g)
  for (let i = 0; i < tokens.length; i++) {
    const token = tokens[i]
    if (!token) continue
    if (/^<\//.test(token)) { stack.pop(); continue }
    const hidden = stack.some(tag => tag.hidden)
    if (/^<br\s*\/?\s*>$/i.test(token) || token === '\n') { if (!hidden) parts.push({kind: 'break'}); continue }
    if (/^</.test(token)) {
      const name = token.slice(1, -1).split(/\s/)[0].toLowerCase()
      // The card describes base values, so conditional active-buff branches
      // must not be concatenated with their unmodified ShowIfNot branch.
      stack.push({name, hidden: hidden || name.startsWith('showif.')})
      continue
    }
    if (hidden) continue
    if (/^%i:/.test(token)) {
      const scaling = scalingNames[token.slice(3, -1).toLowerCase()]
      if (scaling) parts.push({kind: 'icon', scaling})
      continue
    }
    if (token.startsWith('@')) {
      const expression = token.slice(1, -1)
      const values = [1, 2, 3, 4].map(star => spellValue(champion, expression, star))
      const suffix = /^(?:%i:\w+%|\s|&nbsp;|[()%])+/i.exec(tokens.slice(i + 1).join(''))?.[0] ?? ''
      const hints = [...suffix.matchAll(/%i:(\w+)%/gi)].map(match => scalingNames[match[1].toLowerCase()]).filter(Boolean)
      const scaling = hints[0] ?? stack.map(tag => scalingNames[tag.name]).find(Boolean)
      const terms = formulaTerms(champion, expression, hints)
      const split = terms && terms.every(term => term.values.slice(0, 3).every(value => value != null))
        && (terms.some(term => term.percent) || new Set(terms.map(term => term.scaling)).size > 1)
      if (split) {
        if (terms.length > 1) parts.push({kind: 'text', text: '('})
        terms.forEach((term, index) => {
          if (index) parts.push({kind: 'text', text: ' + '})
          parts.push({kind: 'value', values: term.values, scaling: term.scaling})
          if (term.percent) parts.push({kind: 'text', text: '%'})
          if (term.scaling) parts.push({kind: 'text', text: ' '}, {kind: 'icon', scaling: term.scaling})
        })
        if (terms.length > 1) parts.push({kind: 'text', text: ')'})
        // The expanded formula already labels each term. Consume only the
        // original immediately-adjacent stat icons/parentheses, not prose.
        let remaining = suffix.length
        for (let next = i + 1; next < tokens.length && remaining; next++) {
          const length = tokens[next].length
          tokens[next] = tokens[next].slice(remaining)
          remaining = Math.max(0, remaining - length)
        }
        if (suffix) parts.push({kind: 'text', text: ' '})
      } else {
        parts.push(values.every(value => value == null)
          ? {kind: 'unavailable', reason: isLiveValue(champion, expression) ? 'live' : 'missing'}
          : {kind: 'value', values, scaling: terms?.[0]?.scaling ?? scaling})
        // A few Riot strings put the percent sign inside @...@ itself.
        if (expressionParts(expression)?.[4] && !tokens[i + 1]?.startsWith('%')) parts.push({kind: 'text', text: '%'})
      }
    } else if (token.startsWith('{{')) {
      // Unresolved game-state/localization substitutions are explicit, never raw keys.
      parts.push({kind: 'unavailable'})
    } else {
      const scaling = stack.map(tag => scalingNames[tag.name]).find(Boolean)
      parts.push({kind: 'text', text: decode(token), emphasis: stack.some(tag => ['spellpassive', 'spellactive', 'keyword', 'b'].includes(tag.name)), ...(scaling ? {scaling} : {})})
    }
  }
  return parts
}
