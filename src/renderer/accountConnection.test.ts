import {describe, expect, it} from 'vitest'
import {accountConnectionError} from './accountConnection'
import en from './i18n/locales/en.json'
import fr from './i18n/locales/fr.json'
import ko from './i18n/locales/ko.json'

const noQr = 'No QR code found. Display the Riot Client sign-in QR and try again.'
const expired = 'Sign in to Riot again from this account’s profile, then retry.'
const rejected = 'Riot could not approve the connection. Refresh the QR code and try again.'
const fallback = 'Connection failed. Please try again.'

describe('account connection notifications', () => {
  it.each([
    'No readable Riot sign-in QR was found',
    'Riot Client window was not found. Open Riot Client, show its QR code',
    'Riot Client was found, but its sign-in window could not be captured.',
    'Peaks could not capture Riot Client',
    'Missing trusted window capture',
    'The image is not a valid Riot sign-in QR',
  ])('explains missing QR capture without leaking native errors: %s', message => {
    expect(accountConnectionError(new Error(`Error invoking remote method 'peaks:invoke': Error: ${message}`))).toBe(noQr)
  })

  it.each([
    'This identity needs a reusable Riot session before QR Connect.',
    'Riot requires sign-in again for this account.',
    'Reauthentication is required',
    'The saved session has expired',
  ])('asks for sign-in when a saved session needs renewal: %s', message => {
    expect(accountConnectionError(new Error(message))).toBe(expired)
  })

  it.each([
    'Riot could not verify the pending QR session',
    'Riot Client sign-in was not approved',
    'The selected Riot session changed while connecting.',
  ])('distinguishes approval failure from missing QR capture: %s', message => {
    expect(accountConnectionError(new Error(message))).toBe(rejected)
  })

  it.each([
    new Error('Private#EUW token=private-token C:\\Users\\Private\\account.json'),
    'private raw error', {message: 'private details'}, null, undefined,
  ])('uses a safe fallback for unrecognized failures', error => {
    expect(accountConnectionError(error)).toBe(fallback)
  })

  it('has a complete translated notification for each outcome', () => {
    for (const message of [noQr, expired, rejected, fallback]) {
      for (const catalog of [en, fr, ko]) {
        expect(catalog[message as keyof typeof en]?.trim()).toBeTruthy()
      }
      expect(fr[message as keyof typeof en]).not.toBe(message)
      expect(ko[message as keyof typeof en]).not.toBe(message)
    }
  })
})
