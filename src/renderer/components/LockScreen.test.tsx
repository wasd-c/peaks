import {renderToStaticMarkup} from 'react-dom/server'
import {LayerProvider} from '@astryxdesign/core/Layer'
import {describe, expect, it} from 'vitest'
import {FORGOT_CODE_LABEL, LockScreen, RESET_PROMPTS} from './LockScreen'

const renderLockScreen = (mode: 'create' | 'confirm' | 'unlock') =>
  renderToStaticMarkup(
    <LayerProvider>
      <LockScreen
        mode={mode}
        onReset={async () => undefined}
        onSubmit={async () => undefined}
      />
    </LayerProvider>,
  )

describe('LockScreen forgotten passcode recovery', () => {
  it('offers recovery only on the existing-vault unlock screen', () => {
    expect(renderLockScreen('unlock')).toContain(FORGOT_CODE_LABEL)
    expect(renderLockScreen('create')).not.toContain(FORGOT_CODE_LABEL)
    expect(renderLockScreen('confirm')).not.toContain(FORGOT_CODE_LABEL)
  })

  it('uses explicit recovery and irreversible-deletion prompts', () => {
    expect(RESET_PROMPTS.warning.description).toContain('cannot recover your passcode')
    expect(RESET_PROMPTS.warning.description).toContain('only way')
    expect(RESET_PROMPTS.confirmation.description).toContain('cannot be undone')
    expect(RESET_PROMPTS.confirmation.description).toContain('return to onboarding')
    expect(RESET_PROMPTS.confirmation.actionLabel).toBe('Clear all local data')
  })
})
