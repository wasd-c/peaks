import {describe, expect, it} from 'vitest'
import {connectAccountSwitch, recentAccountShortcuts, requestedAccountConnection} from './accountJumpList'

const handle = (digit: string) => `account-${digit.repeat(8)}-${digit.repeat(4)}-${digit.repeat(4)}-${digit.repeat(4)}-${digit.repeat(12)}`
const account = (digit: string, lastConnectedAt: number | null, extra: Record<string, unknown> = {}) => ({
  id: handle(digit), riotId: `player${digit}#EUW`, canConnectQr: true, lastConnectedAt, ...extra,
})

describe('recent account taskbar shortcuts', () => {
  it('lists the three most recently connected accounts that can connect', () => {
    const state = {locked: false, settings: {}, accounts: [
      account('1', 10), account('2', 40, {nickname: 'Main'}), account('3', null), account('4', 30),
      account('5', 50, {canConnectQr: false}), account('6', 20),
    ]}
    expect(recentAccountShortcuts(state)).toEqual([
      {accountId: handle('2'), title: 'Main'},
      {accountId: handle('4'), title: 'player4#EUW'},
      {accountId: handle('6'), title: 'player6#EUW'},
    ])
  })

  it('hides every account while locked or in streamer mode', () => {
    expect(recentAccountShortcuts({locked: true, settings: {}, accounts: [account('1', 1)]})).toEqual([])
    expect(recentAccountShortcuts({locked: false, settings: {streamerMode: true}, accounts: [account('1', 1)]})).toEqual([])
  })

  it('ignores replies that are not an application state', () => {
    expect(recentAccountShortcuts({detected: true})).toBeUndefined()
    expect(recentAccountShortcuts([account('1', 1)])).toBeUndefined()
  })

  it('never puts an internal account identifier on the command line', () => {
    expect(recentAccountShortcuts({locked: false, settings: {}, accounts: [{...account('1', 1), id: 'puuid-or-db-id'}]})).toEqual([])
  })
})

describe('taskbar shortcut command line', () => {
  it('accepts only a renderer account handle', () => {
    expect(requestedAccountConnection(['peaks.exe', `${connectAccountSwitch}=${handle('a')}`])).toBe(handle('a'))
    expect(requestedAccountConnection(['peaks.exe', `${connectAccountSwitch}=../../evil`])).toBeNull()
    expect(requestedAccountConnection(['peaks.exe'])).toBeNull()
  })
})
