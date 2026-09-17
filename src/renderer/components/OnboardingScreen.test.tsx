import {renderToStaticMarkup} from 'react-dom/server'
import {describe, expect, it} from 'vitest'
import {
  ONBOARDING_ACTION,
  ONBOARDING_BODY,
  ONBOARDING_HEADING,
  OnboardingScreen,
} from './OnboardingScreen'

describe('OnboardingScreen', () => {
  it('exposes the exact welcome copy and primary action accessibly', () => {
    const markup = renderToStaticMarkup(<OnboardingScreen onGetStarted={() => undefined} />)

    expect(markup).toContain(ONBOARDING_HEADING)
    expect(markup).toContain(ONBOARDING_BODY)
    expect(markup).toContain(ONBOARDING_ACTION)
    expect(markup).toContain('<h1')
    expect(markup).toContain('<button')
  })

  it('marks the scene as reduced-motion when requested', () => {
    const markup = renderToStaticMarkup(
      <OnboardingScreen onGetStarted={() => undefined} reduceMotion />,
    )

    expect(markup).toContain('data-reduce-motion="true"')
  })
})
