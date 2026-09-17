import {describe, expect, it, vi} from 'vitest'
import type {TotpSetupProposal} from '../types'
import {cancelPendingTotp, canConfirmTotp} from './totpDialog'

const proposal: TotpSetupProposal = {
  confirmationId: 'confirmation-token',
  accountId: 'owned-puuid',
  riotId: 'Peak#EUW',
  expiresInSeconds: 300,
}

describe('Riot authenticator confirmation boundary', () => {
  it('cannot confirm before the explicit confirmation step', () => {
    expect(canConfirmTotp('choices', null)).toBe(false)
    expect(canConfirmTotp('preparing', proposal)).toBe(false)
    expect(canConfirmTotp('saving', proposal)).toBe(false)
    expect(canConfirmTotp('confirming', proposal)).toBe(true)
  })

  it('cancels the pending backend session when the confirmation closes', async () => {
    const cancel = vi.fn(async () => undefined)

    await cancelPendingTotp(proposal, cancel)

    expect(cancel).toHaveBeenCalledOnce()
    expect(cancel).toHaveBeenCalledWith('confirmation-token')
  })

  it('does not issue a cancellation when no proposal exists', async () => {
    const cancel = vi.fn(async () => undefined)

    await cancelPendingTotp(null, cancel)

    expect(cancel).not.toHaveBeenCalled()
  })
})
