import {describe, expect, it} from 'vitest'
import {loadTftChampion, tftChampionEntry, type TftChampion} from './tftCatalog'
import {spellValue, tftSpellParts} from './tftSpell'

const champion = (description: string): TftChampion => ({
  names: {en: 'Test'}, traits: {}, stats: {}, ability: {
    names: {}, descriptions: {en: description}, variables: {Damage: [0, 155, 235, 440, 750], Bonus: [0, 0.1, 0.2, 0.3, 0.4]},
    calculations: {ModifiedDamage: {__type: 'GameCalculation', mFormulaParts: [{__type: 'SubPartScaledProportionalToStat', mRatio: 0.009999999776482582,
      mSubpart: {__type: 'NamedDataValueCalculationPart', mDataValue: 'Damage'}}]}},
  },
})

describe('TFT spell values', () => {
  it('uses Riot star indexes 1–4 and explicit AP formulas', () => {
    const unit = champion('Deal <magicDamage>@ModifiedDamage@ (%i:scaleAP%)</magicDamage>.')
    expect([1, 2, 3, 4].map(star => spellValue(unit, 'ModifiedDamage', star))).toEqual([155, 235, 440, 750])
    expect(tftSpellParts(unit, 'en')).toContainEqual({kind: 'value', values: [155, 235, 440, 750], scaling: 'ap'})
    expect(tftSpellParts(unit, 'en')).toContainEqual({kind: 'icon', scaling: 'ap'})
  })

  it('handles percentage expressions and capitalization without evaluating provider code', () => {
    const unit = champion('@Bonus*100@%')
    expect(spellValue(unit, 'bonus*100', 2)).toBe(20)
    expect(spellValue(unit, 'Bonus/0', 2)).toBeNull()
    expect(spellValue(unit, 'Damage;alert(1)', 2)).toBeNull()
    expect(spellValue(unit, 'ModifiedOtherDamage', 2)).toBeNull()
    expect(spellValue(unit, 'Bonus*100%', 2)).toBe(20)
    expect(tftSpellParts(champion('@Bonus*100%@'), 'en')).toContainEqual({kind: 'text', text: '%'})
    expect([0, -1, 1.5, 5, NaN].map(star => spellValue(unit, 'Damage', star))).toEqual([null, null, null, null, null])
  })

  it('does not invent a formula, zero, or localization for missing values', () => {
    const unit = champion('@Unknown@ {{missing_term}} @Bonus@')
    expect(tftSpellParts(unit, 'fr').filter(p => p.kind === 'unavailable')).toHaveLength(2)
    unit.ability.calculations.Loop = {__type: 'GameCalculationModified', mModifiedGameCalculation: 'Loop'}
    expect(spellValue(unit, 'Loop', 2)).toBeNull()
  })

  it('preserves line breaks and entities while discarding provider tags', () => {
    const parts = tftSpellParts(champion('<spellPassive>Passive:</spellPassive> A&nbsp;&amp;&nbsp;B<br><br>@Bonus@'), 'en')
    expect(parts).toContainEqual({kind: 'text', text: 'Passive:', emphasis: true})
    expect(parts).toContainEqual({kind: 'text', text: ' A & B', emphasis: false})
    expect(parts.filter(p => p.kind === 'break')).toHaveLength(2)
  })

  it('keeps base and augmented spell branches separate', () => {
    const unit = champion('<ShowIf.TFT_Augment_Active><b>5</b></ShowIf.TFT_Augment_Active><ShowIfNot.TFT_Augment_Active>4</ShowIfNot.TFT_Augment_Active> seconds')
    expect(tftSpellParts(unit, 'en').filter(p => p.kind === 'text').map(p => p.text).join('')).toBe('4 seconds')
  })

  it('resolves historical hashed calculation references', () => {
    const unit = champion('@ModifiedDamage@')
    unit.ability.calculations['{f24078df}'] = unit.ability.calculations.ModifiedDamage
    delete unit.ability.calculations.ModifiedDamage
    expect(spellValue(unit, 'ModifiedDamage', 2)).toBe(235)
  })

  it('evaluates explicit exponent, min/max and clamp nodes including hashed type names', () => {
    const unit = champion('@Derived@')
    unit.ability.calculations.Derived = {__type: 'GameCalculation', mFormulaParts: [
      {__type: '{803dae4c}', mFloor: 3, mCeiling: 7, mSubparts: [
        {__type: '{382277da}', mSubparts: [
          {__type: 'ExponentSubPartsCalculationPart', part1: {__type: 'NumberCalculationPart', mNumber: 2}, part2: {__type: 'NumberCalculationPart', mNumber: 3}},
          {__type: 'NumberCalculationPart', mNumber: 9},
        ]},
      ]},
      {__type: '{8a96ea3c}', mSubparts: [{__type: 'NumberCalculationPart'}, {__type: 'NumberCalculationPart', mNumber: -1}]},
    ]}
    expect(spellValue(unit, 'Derived', 2)).toBe(7)
    unit.ability.calculations.InvalidPower = {__type: 'ExponentSubPartsCalculationPart', part1: {__type: 'NumberCalculationPart'}, part2: {__type: 'NumberCalculationPart', mNumber: -1}}
    expect(spellValue(unit, 'InvalidPower', 2)).toBeNull()
  })

  it('distinguishes live counters from missing source data without assuming zero', () => {
    const unit = champion('@Stack@ / @TFTUnitProperty.unit:Stacks@ / @CurrentDamage@ / @Unknown@')
    unit.ability.calculations.CurrentDamage = {__type: 'GameCalculation', mFormulaParts: [
      {__type: 'BuffCounterByCoefficientCalculationPart', mBuffName: 'Stacks', mCoefficient: 3},
    ]}
    expect(tftSpellParts(unit, 'en').filter(part => part.kind === 'unavailable')).toEqual([
      {kind: 'unavailable', reason: 'live'}, {kind: 'unavailable', reason: 'live'},
      {kind: 'unavailable', reason: 'live'}, {kind: 'unavailable', reason: 'missing'},
    ])
    unit.ability.variables.Stack = [0, 5, 5, 5, 5]
    expect(tftSpellParts(unit, 'en')[0]).toMatchObject({kind: 'value', values: [5, 5, 5, 5]})
  })

  it('does not silently treat a bonus-stat formula as the unmodified stat', () => {
    const unit = champion('@BonusDamage@ %i:scaleAP%')
    unit.ability.calculations.BonusDamage = {__type: 'SubPartScaledProportionalToStat', mStatFormula: 2,
      mRatio: 0.01, mSubpart: {__type: 'NamedDataValueCalculationPart', mDataValue: 'Damage'}}
    expect(spellValue(unit, 'BonusDamage', 2)).toBeNull()
    expect(tftSpellParts(unit, 'en')[0]).toMatchObject({kind: 'unavailable'})
  })

  it('requires resolved curvetable values and keeps runtime attributes distinct', () => {
    const unit = champion('@TFTCalculationAttributes.GenericCalc1@ @TFTSpellAttributes.Stack@')
    unit.ability.calculations['TFTCalculationAttributes.GenericCalc1'] = {__type: 'GameCalculationCurveTable',
      terms: [{op: 'add', type: 'runtime'}], values: [0, 0, 0, 0], resolved: false}
    expect(spellValue(unit, 'TFTCalculationAttributes.GenericCalc1', 2)).toBeNull()
    expect(tftSpellParts(unit, 'en').filter(part => part.kind === 'unavailable')).toEqual([
      {kind: 'unavailable', reason: 'live'}, {kind: 'unavailable', reason: 'live'},
    ])
  })

  it('uses published values without guessing an unsupported curvetable pre-add operation', () => {
    const unit = champion('@TFTCalculationAttributes.AttackSpeedCalc1@ %i:scaleAP%')
    unit.ability.calculations['TFTCalculationAttributes.AttackSpeedCalc1'] = {__type: 'GameCalculationCurveTable',
      terms: [{op: 'add', type: 'scaled', scaling: 'AbilityPower', coefficient: [1.9, 2, 2.3, 2.6]},
        {op: 'add', type: 'scaled', scaling: 'AbilityPower', coefficient: [-1, -1, -1, -1], preAdd: [-1, -1, -1, -1]}],
      values: [1.9, 2, 2.3, 2.6], resolved: true}
    expect(tftSpellParts(unit, 'en')[0]).toEqual({kind: 'value', values: [1.9, 2, 2.3, 2.6], scaling: 'ap'})
  })
})

describe('bundled TFT set archive', () => {
  it('finds the same champion in older and newer sets by exact Riot ID', async () => {
    const previous = await loadTftChampion('TFT10_Ahri', 10)
    const later = await loadTftChampion('TFT16_Ahri', 16)
    expect(previous?.ability.names.en).toBe('POP/STAR')
    expect(later?.ability.names.en).toBe('Fox-Fire')
    expect(tftChampionEntry('TFT16_Ahri', 16)?.variant).toBe('TFTSet16_PVEMODE')
    expect(tftChampionEntry('TFT10_Ahri', 16)).toBeUndefined()
    expect(tftChampionEntry('TFT999_Ahri')).toBeUndefined()
  })

  it('loads a current champion with localized mana and cast scaling', async () => {
    const gwen = await loadTftChampion('TFT17_Gwen')
    expect(gwen?.stats.mana).toBe(30)
    expect(gwen?.ability.names.fr).toBeTruthy()
    expect(gwen && spellValue(gwen, 'ModifiedDamage', 3)).toBe(440)
  })

  it('keeps modern mixed AD/AP terms separate so each active star has the correct color', async () => {
    const belveth = await loadTftChampion('TFT17_Belveth')
    expect(belveth).toBeDefined()
    expect(spellValue(belveth!, 'TotalDamage', 2)).toBe(38)
    const parts = tftSpellParts(belveth!, 'en')
    expect(parts).toContainEqual({kind: 'value', values: [22, 33, 50, 85], scaling: 'ad'})
    expect(parts).toContainEqual({kind: 'value', values: [3, 5, 7, 12], scaling: 'ap'})
    expect(parts.filter(part => part.kind === 'icon' && (part.scaling === 'ad' || part.scaling === 'ap'))).toEqual([
      {kind: 'icon', scaling: 'ad'}, {kind: 'icon', scaling: 'ap'},
    ])
    expect(parts.filter(part => part.kind === 'text').map(part => part.text).join('')).toContain('physical damage each.')
  })

  it('shows an explicit health coefficient instead of fabricating star-scaled health', async () => {
    const nasus = await loadTftChampion('TFT17_Nasus')
    expect(nasus).toBeDefined()
    expect(spellValue(nasus!, 'ModifiedDamage', 2)).toBeNull()
    const parts = tftSpellParts(nasus!, 'en')
    expect(parts).toContainEqual({kind: 'value', values: [2, 2, 2, 2], scaling: 'health'})
    expect(parts).toContainEqual({kind: 'text', text: '%'})
    expect(parts).toContainEqual({kind: 'value', values: [30, 45, 70, 120], scaling: 'ap'})
    // The one remaining unresolved localization is unrelated to damage math.
    expect(parts.filter(part => part.kind === 'unavailable')).toHaveLength(1)
  })

  it('resolves archived AD coefficients and distinguishes damage type from scaling stat', async () => {
    const akali = await loadTftChampion('TFT10_Akali')
    expect(akali).toBeDefined()
    const parts = tftSpellParts(akali!, 'en')
    expect(parts).toContainEqual({kind: 'value', values: [190, 190, 380, 0], scaling: 'ad'})
    expect(parts).toContainEqual({kind: 'value', values: [80, 120, 400, 2], scaling: 'ap'})
    expect(parts.filter(part => part.kind === 'unavailable')).toEqual([{kind: 'unavailable', reason: 'live'}])
  })

  it('distributes an explicit scalar multiplier over mixed AD and armor terms', async () => {
    const aatrox = await loadTftChampion('TFT17_Aatrox')
    expect(aatrox).toBeDefined()
    const ability = {...aatrox!.ability, descriptions: {en: '@ModifiedNovaDamage@ (%i:scaleAD%%i:scaleArmor%)'}}
    const parts = tftSpellParts({...aatrox!, ability}, 'en')
    expect(parts).toContainEqual({kind: 'value', values: [52, 78, 117, 195], scaling: 'ad'})
    expect(parts).toContainEqual({kind: 'value', values: [117, 175.5, 263.25, 448.5], scaling: 'armor'})
    expect(parts.filter(part => part.kind === 'unavailable')).toHaveLength(0)
    // Conditional N.O.V.A. activation is still not asserted for a base card.
    expect(tftSpellParts(aatrox!, 'en').filter(part => part.kind === 'text').map(part => part.text).join('')).not.toContain('N.O.V.A.')
  })

  it('loads Veigar 18 curvetable damage and percentage rows with the correct star indexes', async () => {
    // MetaTFT's published TFTSet18 curvetable snapshot, also shown in the supplied reference.
    const veigar = await loadTftChampion('DA_18_Veigar', 18)
    expect(veigar).toBeDefined()
    expect([1, 2, 3, 4].map(star => spellValue(veigar!, 'TFTCalculationAttributes.MagicDamageCalc1', star)))
      .toEqual([175, 265, 395, 670])
    expect([1, 2, 3, 4].map(star => spellValue(veigar!, 'TFTCalculationAttributes.MagicDamageCalc2', star)))
      .toEqual([265, 400, 595, 1015])
    for (const language of ['en', 'fr', 'ko']) {
      const parts = tftSpellParts(veigar!, language)
      expect(parts).toContainEqual({kind: 'value', values: [175, 265, 395, 670], scaling: 'ap'})
      expect(parts).toContainEqual({kind: 'value', values: [265, 400, 595, 1015], scaling: 'ap'})
      expect(parts).toContainEqual(expect.objectContaining({kind: 'value', values: [30, 30, 30, 30]}))
      expect(parts.filter(part => part.kind === 'unavailable')).toEqual([{kind: 'unavailable', reason: 'live'}])
    }
  })

  it('retains each scaling term in Camille 18 instead of coloring a mixed total as only AD', async () => {
    const camille = await loadTftChampion('DA_18_Camille', 18)
    expect(camille).toBeDefined()
    expect(spellValue(camille!, 'TFTCalculationAttributes.PhysicalDamageCalc1', 2)).toBe(255)
    const parts = tftSpellParts(camille!, 'fr')
    expect(parts).toContainEqual({kind: 'value', values: [160, 240, 410, 700], scaling: 'ad'})
    expect(parts).toContainEqual({kind: 'value', values: [10, 15, 25, 40], scaling: 'ap'})
    expect(parts.filter(part => part.kind === 'unavailable')).toHaveLength(0)
  })

  it('resolves nested curvetable references while preserving Alistar 18 health coefficients', async () => {
    const alistar = await loadTftChampion('DA_18_Alistar', 18)
    expect(alistar).toBeDefined()
    const parts = tftSpellParts(alistar!, 'en')
    expect(parts).toContainEqual({kind: 'value', values: [200, 260, 320, 380], scaling: 'ap'})
    expect(parts).toContainEqual({kind: 'value', values: [8, 8, 8, 8], scaling: 'health'})
    expect(parts).toContainEqual({kind: 'text', text: '%'})
    expect(parts.filter(part => part.kind === 'unavailable')).toHaveLength(0)
  })

  it('requires set context for shared NPC identifiers', () => {
    expect(tftChampionEntry('TFT_TrainingDummy')).toBeUndefined()
    expect(tftChampionEntry('TFT_TrainingDummy', 17)?.set).toBe(17)
    expect(tftChampionEntry('TFT_TrainingDummy', 10)?.set).toBe(10)
  })

  it('keeps champions removed by a half-set even when the core name is reused', async () => {
    expect((await loadTftChampion('TFT6_Katarina', 6, 'TFT_Set6'))?.names.en).toBe('Katarina')
    expect((await loadTftChampion('TFT3_Kassadin', 3, 'TFTSet3'))?.names.en).toBe('Kassadin')
  })
})
