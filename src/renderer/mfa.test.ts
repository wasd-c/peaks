import {describe, expect, it} from 'vitest'
import {riotMfaError} from './mfa'

describe('MFA user-facing failures', () => {
  it.each([
    'Save a reusable Riot session for this account before setting up Riot MFA',
    'Riot session expired',
    'MFA_SESSION_REQUIRED',
    'Reconnect this account in Peaks before enabling MFA',
  ])('explains when a fresh Riot sign-in is required: %s', message => {
    expect(riotMfaError(new Error(message)))
      .toBe('Sign in to Riot again from this account’s profile, then retry.')
  })

  it('points a real Riot verification challenge to the fresh sign-in action, not the QR action', () => {
    expect(riotMfaError(new Error('Riot needs you to verify this account again before enabling MFA')))
      .toBe('Riot requires a fresh sign-in to enable MFA. Choose Refresh Riot sign-in from this account’s connection menu, then retry.')
  })

  it('explains a confirmed verification-code challenge without exposing Riot data', () => {
    expect(riotMfaError(new Error("Riot requires a verification code before changing MFA. Use Refresh Riot sign-in from this account's connection menu.")))
      .toBe('Riot requires a verification code to enable MFA. Choose Refresh Riot sign-in from this account’s connection menu, then retry.')
  })

  it('explains the confirmed password challenge', () => {
    expect(riotMfaError(new Error("Riot requires a fresh sign-in before changing MFA. Use Refresh Riot sign-in from this account's connection menu.")))
      .toBe('Riot requires a fresh sign-in to enable MFA. Choose Refresh Riot sign-in from this account’s connection menu, then retry.')
  })

  it.each([
    'Riot could not complete the account connection. Please try again',
    'Riot rejected authenticator enrollment (HTTP 403). Sign in and check email MFA.',
  ])('does not mistake an HTTP rejection for an expired session: %s', message => {
    expect(riotMfaError(new Error(message)))
      .toBe('Riot could not complete the account connection. Please try again.')
  })

  it('distinguishes a blocked request from an account verification request', () => {
    expect(riotMfaError(new Error('Riot blocked the account connection. Please try again later')))
      .toBe('Riot blocked the account connection. Please try again later.')
  })

  it('explains the email prerequisite without displaying a response body', () => {
    expect(riotMfaError(new Error('Enable email multi-factor authentication in Riot account security, then try again')))
      .toBe('Enable email MFA in your Riot account first, then try again.')
  })

  it('explains existing authenticators will not be replaced', () => {
    expect(riotMfaError(new Error('Riot Mobile authentication is already enabled; Peaks will not rotate it')))
      .toBe('An authenticator is already enabled on this Riot account. Peaks will not replace it.')
  })

  it('does not claim a saved code proves the authenticator is active', () => {
    expect(riotMfaError(new Error('An authenticator secret is already saved for this account; Peaks will not replace it')))
      .toBe('An authenticator is already saved for this account. Copy its code from the account actions menu.')
  })

  it.each([new Error('HTTP 502 body=secret identity=Private#EUW'), 'opaque response', null])(
    'never displays unknown internal error details', error => {
      expect(riotMfaError(error)).toBe('MFA could not be enabled. Please try again.')
    },
  )
})
