import {describe, expect, it} from 'vitest'

import {
  gameArtwork,
  hasExactValorantRankAsset,
  localAsset,
  rankAsset,
  valorantAgentAsset,
  valorantAgentName,
  valorantAgentPortraitAsset,
  valorantMapAsset,
  valorantMapName,
} from './assets'

const expectLocalPng = (value: string | undefined) => {
  expect(value).toBeTruthy()
  expect(value).toMatch(/\.png(?:\?|$)/)
  expect(value).not.toMatch(/^https?:\/\//)
}

describe('local Riot asset resolution', () => {
  it('bundles shared local brand artwork after disabling publicDir', () => {
    const brandMark = localAsset('peaks-mark.svg')

    expect(
      brandMark.startsWith('data:image/svg+xml') || /\.svg(?:\?|$)/.test(brandMark),
    ).toBe(true)
    expect(brandMark).not.toMatch(/^https?:\/\//)
  })

  it('resolves rank emblems through bundled Vite URLs', () => {
    expectLocalPng(rankAsset('VALORANT', 'Ascendant 2'))
    expectLocalPng(rankAsset('League of Legends', 'Diamond IV'))
  })

  it('uses exact Valorant divisions and the bundled unranked fallback', () => {
    const ascendantOne = rankAsset('VALORANT', 'Ascendant 1')
    const ascendantThree = rankAsset('VALORANT', 'Ascendant 3')
    const unranked = rankAsset('VALORANT', 'Unranked')

    expectLocalPng(ascendantThree)
    expect(ascendantThree).not.toBe(ascendantOne)
    expect(rankAsset('VALORANT', 'Rank unavailable')).toBe(unranked)
    expect(hasExactValorantRankAsset('Diamond 2')).toBe(true)
    expect(hasExactValorantRankAsset('Diamond')).toBe(false)
  })

  it('resolves agents by display name or UUID without a network URL', () => {
    const omenUuid = '8e253930-4c05-31dd-1b6c-968525494517'

    expect(valorantAgentAsset('omen')).toBe(valorantAgentAsset(omenUuid))
    expectLocalPng(valorantAgentAsset('Omen'))
    expect(valorantAgentAsset('Unknown agent')).toBeUndefined()
  })

  it('uses a separate locally bundled full portrait for standing player cards', () => {
    const omenUuid = '8e253930-4c05-31dd-1b6c-968525494517'
    const portrait = valorantAgentPortraitAsset('Omen')

    expectLocalPng(portrait)
    expect(portrait).toBe(valorantAgentPortraitAsset(omenUuid))
    expect(portrait).not.toBe(valorantAgentAsset('Omen'))
    expect(valorantAgentName(omenUuid)).toBe('Omen')
    expect(valorantAgentPortraitAsset('Unknown agent')).toBeUndefined()
  })

  it('resolves maps by display name, UUID, map URL, or internal map name', () => {
    const abyssUuid = '224b0a95-48b9-f703-1bd8-67aca101a61f'
    const abyssMapUrl = '/Game/Maps/Infinity/Infinity'
    const abyssAsset = valorantMapAsset('Abyss')

    expectLocalPng(abyssAsset)
    expect(valorantMapAsset(abyssUuid)).toBe(abyssAsset)
    expect(valorantMapAsset(abyssMapUrl)).toBe(abyssAsset)
    expect(valorantMapAsset('Infinity')).toBe(abyssAsset)
    expect(valorantMapName(abyssMapUrl)).toBe('Abyss')
    expect(valorantMapName('Port')).toBe('Icebox')
  })

  it('uses a bundled local fallback for unknown Valorant maps', () => {
    expectLocalPng(valorantMapAsset('Unknown map'))
    expectLocalPng(gameArtwork('VALORANT'))
  })
})
