import {describe, expect, it} from 'vitest'
import {AutoLockCoordinator, pausesAutoLock} from './autoLock'

const settings = {
  autoLockMinutes: 1,
  // Older profiles can still contain this field. It is intentionally inert.
  lockOnBlur: true,
}

describe('automatic lock coordination', () => {
  it('recognizes every Riot browser operation that must pause locking', () => {
    expect(pausesAutoLock('add_account')).toBe(true)
    expect(pausesAutoLock('import_session')).toBe(true)
    expect(pausesAutoLock('prepare_totp_setup')).toBe(true)
    expect(pausesAutoLock('confirm_totp_setup')).toBe(true)
    expect(pausesAutoLock('enable_riot_mfa')).toBe(true)
    expect(pausesAutoLock('connect_riot_client')).toBe(true)
    expect(pausesAutoLock('connect_riot_qr_image')).toBe(true)
    expect(pausesAutoLock('refresh')).toBe(false)
  })

  it('ignores inactivity while a Riot browser operation is pending', () => {
    const coordinator = new AutoLockCoordinator(0)
    const resume = coordinator.pause()

    expect(coordinator.tryBeginLock('inactivity', settings, 120_000)).toBe(false)

    resume(120_000)
    expect(coordinator.tryBeginLock('inactivity', settings, 179_999)).toBe(false)
    expect(coordinator.tryBeginLock('inactivity', settings, 180_000)).toBe(true)
  })

  it('locks only at the configured timeout regardless of a legacy blur preference', () => {
    const legacyEnabled = new AutoLockCoordinator(0)
    const legacyDisabled = new AutoLockCoordinator(0)
    const timeoutSettings = {...settings, autoLockMinutes: 15}
    const legacyDisabledSettings = {...timeoutSettings, lockOnBlur: false}

    expect(legacyEnabled.tryBeginLock('inactivity', timeoutSettings, 899_999)).toBe(false)
    expect(
      legacyDisabled.tryBeginLock(
        'inactivity',
        legacyDisabledSettings,
        899_999,
      ),
    ).toBe(false)
    expect(legacyEnabled.tryBeginLock('inactivity', timeoutSettings, 900_000)).toBe(true)
    expect(
      legacyDisabled.tryBeginLock(
        'inactivity',
        legacyDisabledSettings,
        900_000,
      ),
    ).toBe(true)
  })

  it('resets inactivity from normal user activity', () => {
    const coordinator = new AutoLockCoordinator(0)

    coordinator.recordActivity(59_000)

    expect(coordinator.tryBeginLock('inactivity', settings, 60_000)).toBe(false)
    expect(coordinator.tryBeginLock('inactivity', settings, 119_000)).toBe(true)
  })

  it('allows explicit manual locking and prevents duplicate lock requests', () => {
    const coordinator = new AutoLockCoordinator(0)

    expect(coordinator.tryBeginLock('manual', settings, 1_000)).toBe(true)
    expect(coordinator.tryBeginLock('manual', settings, 1_001)).toBe(false)

    coordinator.releaseFailedLock(2_000)
    expect(coordinator.tryBeginLock('manual', settings, 2_001)).toBe(true)
  })

  it('keeps close-only mode unlocked through inactivity and still permits manual locking', () => {
    const coordinator = new AutoLockCoordinator(0)
    const closeOnly = {...settings, autoLockMinutes: 0}
    expect(coordinator.tryBeginLock('inactivity', closeOnly, 180 * 24 * 60 * 60_000)).toBe(false)
    expect(coordinator.tryBeginLock('manual', closeOnly, 180 * 24 * 60 * 60_000)).toBe(true)
    expect(pausesAutoLock('change_pin')).toBe(true)
  })

  it('supports nested pauses without resuming too early', () => {
    const coordinator = new AutoLockCoordinator(0)
    const resumeFirst = coordinator.pause()
    const resumeSecond = coordinator.pause()

    resumeFirst(60_000)
    expect(coordinator.tryBeginLock('inactivity', settings, 120_000)).toBe(false)

    resumeSecond(121_000)
    resumeSecond(122_000)
    expect(coordinator.tryBeginLock('inactivity', settings, 180_999)).toBe(false)
    expect(coordinator.tryBeginLock('inactivity', settings, 181_000)).toBe(true)
  })
})
