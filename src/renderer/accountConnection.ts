export interface AccountConnection {
  accountId: string
  phase: 'pending' | 'approved' | 'leaving'
}

/** User-facing categories only: never expose raw bridge/auth details in a toast. */
export function accountConnectionError(error: unknown): string {
  const message = error instanceof Error ? error.message : ''
  if (/could not switch accounts/i.test(message)) {
    return 'Riot cannot switch accounts right now. Finish the current game or sign out, then retry.'
  }
  if (/Riot Client was not found/i.test(message)) {
    return 'Install Riot Client, then try Connect again.'
  }
  if (/has not finished closing|could not restart after sign-out/i.test(message)) {
    return 'Riot Client could not restart. A game may still be starting. Close Riot Client, then try Connect again.'
  }
  if (/taking too long to open|could not open|not ready for QR|could not prepare QR|could not create a QR|did not return a QR|invalid sign-in state|has not finished signing out|has not finished signing in|could not finish signing in/i.test(message)) {
    return 'Riot Client is not ready. Wait a moment and try Connect again.'
  }
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
