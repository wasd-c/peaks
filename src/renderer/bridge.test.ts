import {describe, expect, it} from 'vitest'
import {invoke} from './bridge'
import type {AppState, TotpSetupProposal, TotpSetupResult} from './types'

Object.defineProperty(globalThis, 'window', {
  configurable: true,
  value: {},
})

describe('web bridge account connection', () => {
  it('changes the code only after verifying the current code and preserves accounts', async () => {
    const before = await invoke<AppState>('pin', {pin: '2580'})
    await expect(invoke('change_pin', {oldPin: '9999', newPin: '2468', confirmPin: '2468'})).rejects.toThrow('current passcode')
    await expect(invoke('change_pin', {oldPin: '2580', newPin: '2468', confirmPin: '1357'})).rejects.toThrow('do not match')
    const changed = await invoke<AppState>('change_pin', {oldPin: '2580', newPin: '2468', confirmPin: '2468'})
    expect(changed.accounts).toEqual(before.accounts)
    await invoke('lock')
    await expect(invoke('pin', {pin: '2580'})).rejects.toThrow('not recognized')
    await invoke('pin', {pin: '2468'})
    await invoke('change_pin', {oldPin: '2468', newPin: '2580', confirmPin: '2580'})
  })

  it('uses the Watchlist command while retaining the legacy toggle alias', async () => {
    const unlocked = await invoke<AppState>('pin', {pin: '2580'})
    const player = unlocked.followed[0]

    const unwatched = await invoke<AppState>('toggle_watchlist', {player})
    expect(unwatched.followed.some(candidate => candidate.id === player.id)).toBe(false)
    expect(unwatched.operationNotice).toBe('Removed from Watchlist')

    const watched = await invoke<AppState>('toggle_follow', {player})
    expect(watched.followed.some(candidate => candidate.id === player.id)).toBe(true)
    expect(watched.operationNotice).toBe('Added to Watchlist')
  })

  it('adds an authenticated account without user-entered identity data', async () => {
    const unlocked = await invoke<AppState>('pin', {pin: '2580'})
    const next = await invoke<AppState>('add_account', {})
    const account = next.accounts[next.accounts.length - 1]

    expect(next.accounts).toHaveLength(unlocked.accounts.length + 1)
    expect(account).toMatchObject({
      connected: true,
      owned: true,
      region: 'EUW',
    })
    expect(account.riotId).toMatch(/#EUW$/)
  })

  it('removes an account from local renderer state', async () => {
    const unlocked = await invoke<AppState>('pin', {pin: '2580'})
    const account = unlocked.accounts[0]

    const next = await invoke<AppState>('remove_account', {accountId: account.id})

    expect(next.accounts.some(candidate => candidate.id === account.id)).toBe(false)
    await expect(invoke<AppState>('remove_account', {accountId: account.id})).rejects.toThrow(
      'That account is no longer available',
    )
  })

  it('requires a separate confirmation before saving an authenticator secret', async () => {
    const unlocked = await invoke<AppState>('pin', {pin: '2580'})
    const account = unlocked.accounts.find(candidate => !candidate.hasTotp)
    expect(account).toBeDefined()

    const proposal = await invoke<TotpSetupProposal>('prepare_totp_setup', {
      accountId: account?.id,
    })
    const unchanged = await invoke<AppState>('state')
    expect(unchanged.accounts.find(candidate => candidate.id === account?.id)?.hasTotp).toBe(false)

    const result = await invoke<TotpSetupResult>('confirm_totp_setup', {
      accountId: proposal.accountId,
      confirmationId: proposal.confirmationId,
    })
    expect(result.seedSaved).toBe(true)
    expect(result.verified).toBe(true)
    expect(result.state.accounts.find(candidate => candidate.id === account?.id)?.hasTotp).toBe(true)
  })
})
