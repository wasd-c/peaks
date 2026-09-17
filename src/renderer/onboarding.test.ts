import {describe, expect, it} from 'vitest'
import {
  ONBOARDING_COMPLETION_KEY,
  clearOnboardingCompletion,
  isFirstRunPreview,
  persistOnboardingCompletion,
  readOnboardingCompletion,
  shouldShowOnboarding,
  type OnboardingStorage,
} from './onboarding'

const memoryStorage = (): OnboardingStorage => {
  const values = new Map<string, string>()
  return {
    getItem: key => values.get(key) ?? null,
    removeItem: key => values.delete(key),
    setItem: (key, value) => values.set(key, value),
  }
}

describe('first-run onboarding gate', () => {
  it('never interrupts a profile that already has a passcode', () => {
    expect(shouldShowOnboarding(true, false)).toBe(false)
    expect(shouldShowOnboarding(true, true)).toBe(false)
  })

  it('appears before passcode creation only until Get started is persisted', () => {
    const storage = memoryStorage()

    expect(readOnboardingCompletion(storage)).toBe(false)
    expect(shouldShowOnboarding(false, false)).toBe(true)

    persistOnboardingCompletion(storage)

    expect(storage.getItem(ONBOARDING_COMPLETION_KEY)).toBe('complete')
    expect(readOnboardingCompletion(storage)).toBe(true)
    expect(shouldShowOnboarding(false, true)).toBe(false)

    clearOnboardingCompletion(storage)

    expect(storage.getItem(ONBOARDING_COMPLETION_KEY)).toBeNull()
  })

  it('continues safely when browser storage is unavailable', () => {
    const unavailable: OnboardingStorage = {
      getItem: () => {
        throw new Error('blocked')
      },
      removeItem: () => {
        throw new Error('blocked')
      },
      setItem: () => {
        throw new Error('blocked')
      },
    }

    expect(readOnboardingCompletion(unavailable)).toBe(false)
    expect(() => persistOnboardingCompletion(unavailable)).not.toThrow()
    expect(() => clearOnboardingCompletion(unavailable)).not.toThrow()
  })

  it('recognizes only the explicit direct-web first-run preview flag', () => {
    expect(isFirstRunPreview('?firstRun=1')).toBe(true)
    expect(isFirstRunPreview('?firstRun=0')).toBe(false)
    expect(isFirstRunPreview('')).toBe(false)
  })
})
