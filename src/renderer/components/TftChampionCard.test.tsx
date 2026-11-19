import {renderToStaticMarkup} from 'react-dom/server'
import {describe, expect, it} from 'vitest'
import {TftSpellDescription} from './TftChampionCard'

describe('TFT spell rank emphasis', () => {
  it.each([1, 2, 3, 4])('emphasizes only the actual %i-star rank', stars => {
    const markup = renderToStaticMarkup(<TftSpellDescription stars={stars} parts={[{kind: 'value', values: [155, 235, 440, 750], scaling: 'ap'}]} />)
    expect(markup.match(/data-active="true"/g)).toHaveLength(1)
    expect(markup.match(/data-active="false"/g)).toHaveLength(stars === 4 ? 3 : 2)
    expect(markup).toContain(`data-active="true" data-scaling="ap"`)
    expect(markup).toContain(`aria-label="${stars} stars: ${[155, 235, 440, 750][stars - 1]}"`)
    expect(markup).toContain('[ ')
    expect(markup).toContain(' ]')
    expect(markup).toContain(' / ')
  })

  it('does not show three copies of a constant or a fake active rank', () => {
    const constant = renderToStaticMarkup(<TftSpellDescription stars={2} parts={[{kind: 'value', values: [3, 3, 3, 3]}]} />)
    expect(constant).not.toContain('[')
    const unknown = renderToStaticMarkup(<TftSpellDescription stars={0} parts={[{kind: 'value', values: [1, 2, 3, 4]}]} />)
    expect(unknown).not.toContain('data-active="true"')
  })

  it('uses bundled Riot glyphs and distinguishes combat values from missing data', () => {
    const markup = renderToStaticMarkup(<TftSpellDescription stars={2} parts={[
      {kind: 'icon', scaling: 'ap'}, {kind: 'icon', scaling: 'ad'},
      {kind: 'unavailable', reason: 'live'}, {kind: 'unavailable', reason: 'missing'},
    ]} />)
    expect(markup).toContain('alt="Ability power"')
    expect(markup).toContain('alt="Attack damage"')
    expect(markup).toMatch(/src="[^"]+" alt="Ability power"/)
    expect(markup).toContain('This value changes during combat.')
    expect(markup).toContain('This value is missing from the set data.')
    expect(markup).not.toContain('—')
    expect(markup).not.toContain('<svg')
  })
})
