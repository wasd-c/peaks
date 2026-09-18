/** Only known user-facing messages leave the MFA boundary; never show Riot responses. */
export function riotMfaError(error: unknown): string {
  const message = error instanceof Error ? error.message : ''
  if (/Riot blocked the account connection/i.test(message)) {
    return 'Riot blocked the account connection. Please try again later.'
  }
  if (/Riot could not complete the account connection|HTTP (401|403)/i.test(message)) {
    return 'Riot could not complete the account connection. Please try again.'
  }
  if (/Riot requires a verification code before changing MFA/i.test(message)) {
    return 'Riot requires a verification code to enable MFA. Choose Refresh Riot sign-in from this account’s connection menu, then retry.'
  }
  if (/verify this account again before enabling MFA|Riot requires a fresh sign-in before changing MFA/i.test(message)) {
    return 'Riot requires a fresh sign-in to enable MFA. Choose Refresh Riot sign-in from this account’s connection menu, then retry.'
  }
  if (/MFA_SESSION_REQUIRED|reusable Riot session|requires sign-in again|reauthentication|session.*expired|sign in.*again|sign-in.*required|session.*unavailable|Reconnect this account/i.test(message)) {
    return 'Sign in to Riot again from this account’s profile, then retry.'
  }
  if (/Enable email (multi-factor authentication in Riot account security|MFA in your Riot account first)/i.test(message)) {
    return 'Enable email MFA in your Riot account first, then try again.'
  }
  if (/authenticator.*already.*saved/i.test(message)) {
    return 'An authenticator is already saved for this account. Copy its code from the account actions menu.'
  }
  if (/already.*(enabled|authenticator|factor)|existing.*(authenticator|factor)|MFA_ALREADY_ENABLED/i.test(message)) {
    return 'An authenticator is already enabled on this Riot account. Peaks will not replace it.'
  }
  return 'MFA could not be enabled. Please try again.'
}

export const MFA_VERIFICATION_WARNING = 'Authenticator saved, but Riot could not confirm activation. Keep this account in Peaks so you can still copy its codes.'
