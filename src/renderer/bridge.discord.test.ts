import {beforeEach, describe, expect, it, vi} from 'vitest'

interface PreviewStatus {
  enabled: boolean
  applicationId: string
  status: string
  detail: string
}

beforeEach(() => {
  vi.resetModules()
  vi.stubGlobal('window', {})
})

const unlockedBridge = async () => {
  const {invoke} = await import('./bridge')
  await invoke('pin', {pin: '2580'})
  return invoke
}

describe('Discord browser preview boundary', () => {
  it('uses the public application ID and reports preview even when enabled', async () => {
    const invoke = await unlockedBridge()
    const status = await invoke<PreviewStatus>('discord_presence', {enabled: true})
    expect(status).toMatchObject({enabled: true, applicationId: '1549634813756178503', status: 'preview'})
    expect(status.detail).toContain('Demo activity is never published')
  })

  it('preserves independent settings and discards browser configuration on module reload', async () => {
    const invoke = await unlockedBridge()
    await invoke('discord_presence', {enabled: false})
    expect(await invoke('discord_presence', {applicationId: ' 123456789012345678 '})).toMatchObject({
      enabled: false, applicationId: '123456789012345678', status: 'preview',
    })
    expect(await invoke('discord_presence')).toMatchObject({enabled: false, applicationId: '123456789012345678'})
    vi.resetModules()
    const reloaded = await unlockedBridge()
    expect(await reloaded('discord_presence')).toMatchObject({enabled: true, applicationId: '1549634813756178503'})
  })

  it('rejects malformed IDs and unexpected credential fields without changing configuration', async () => {
    const invoke = await unlockedBridge()
    const before = await invoke('discord_presence')
    for (const payload of [
      {applicationId: 'not-an-application-id'},
      {applicationId: '1234567890123456'},
      {applicationId: '123456789012345678901'},
      {applicationId: 123},
      {enabled: 'true'},
      {token: 'should-not-be-accepted'},
    ]) {
      await expect(invoke('discord_presence', payload)).rejects.toThrow()
      expect(await invoke('discord_presence')).toEqual(before)
    }
    expect(await invoke('discord_presence', {applicationId: ''})).toMatchObject({applicationId: '', status: 'preview'})
  })

  it('keeps locked browser configuration inaccessible', async () => {
    const invoke = await unlockedBridge()
    await invoke('lock')
    await expect(invoke('discord_presence', {enabled: true})).rejects.toThrow('Unlock Peaks')
  })
})
