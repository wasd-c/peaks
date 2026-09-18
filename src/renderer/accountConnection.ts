export interface AccountConnection {
  accountId: string
  phase: 'pending' | 'approved' | 'leaving'
}

/** User-facing categories only: never expose raw bridge/auth details in a toast. */
export function accountConnectionError(error: unknown): string {
  const message = error instanceof Error ? error.message : ''
  if (/no readable Riot sign-in QR|window was not found|could not be captured|could not capture Riot|trusted window capture|not a valid Riot sign-in QR/i.test(message)) {
    return 'No QR code found. Display the Riot Client sign-in QR and try again.'
  }
  if (/reusable Riot session|requires sign-in again|reauthentication|saved session.*expired/i.test(message)) {
    return 'Sign in to Riot again from this account’s profile, then retry.'
  }
  if (/pending QR session|sign-in was not approved|selected Riot session changed/i.test(message)) {
    return 'Riot could not approve the connection. Refresh the QR code and try again.'
  }
  return 'Connection failed. Please try again.'
}
