import type {TotpSetupProposal} from '../types'

export type TotpDialogState =
  | 'choices'
  | 'connecting'
  | 'preparing'
  | 'confirming'
  | 'saving'
  | 'partial'

export function canConfirmTotp(
  state: TotpDialogState,
  proposal: TotpSetupProposal | null,
): proposal is TotpSetupProposal {
  return state === 'confirming' && proposal !== null
}

export async function cancelPendingTotp(
  proposal: TotpSetupProposal | null,
  cancel: (confirmationId: string) => Promise<void>,
): Promise<void> {
  if (!proposal) return
  await cancel(proposal.confirmationId).catch(() => undefined)
}
