export const ONBOARDING_COMPLETION_KEY = 'peaks.onboarding.v1.complete'

export interface OnboardingStorage {
  getItem(key: string): string | null
  removeItem(key: string): void
  setItem(key: string, value: string): void
}

export const getOnboardingStorage = (): OnboardingStorage | null => {
  try {
    return typeof window === 'undefined' ? null : window.localStorage
  } catch {
    return null
  }
}

export const readOnboardingCompletion = (storage: OnboardingStorage | null): boolean => {
  try {
    return storage?.getItem(ONBOARDING_COMPLETION_KEY) === 'complete'
  } catch {
    return false
  }
}

export const persistOnboardingCompletion = (storage: OnboardingStorage | null): void => {
  try {
    storage?.setItem(ONBOARDING_COMPLETION_KEY, 'complete')
  } catch {
    // The in-memory React state still advances when storage is unavailable.
  }
}

export const clearOnboardingCompletion = (storage: OnboardingStorage | null): void => {
  try {
    storage?.removeItem(ONBOARDING_COMPLETION_KEY)
  } catch {
    // React still returns to onboarding when browser storage is unavailable.
  }
}

export const isFirstRunPreview = (search: string): boolean =>
  new URLSearchParams(search).get('firstRun') === '1'

export const shouldShowOnboarding = (hasPasscode: boolean, onboardingComplete: boolean): boolean =>
  !hasPasscode && !onboardingComplete
