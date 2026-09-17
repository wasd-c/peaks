import {renderToStaticMarkup} from 'react-dom/server'
import {LayerProvider} from '@astryxdesign/core/Layer'
import {describe, expect, it} from 'vitest'
import {updateControl, type UpdateState} from '../updateState'
import {UpdateControl} from './SidebarUpdate'

const state = (phase: UpdateState['phase'], extra: Partial<UpdateState> = {}): UpdateState => ({phase, currentVersion: '0.3.0', version: '0.4.0', message: 'Update and restart Peaks.', ...extra})
const render = (value: UpdateState) => renderToStaticMarkup(<LayerProvider><UpdateControl state={value} onAction={() => undefined} /></LayerProvider>)

describe('sidebar app update', () => {
  it('offers a direct update and restart action with a visible sidebar notice', () => {
    const html = render(state('available'))
    expect(html).toContain('Update to Peaks 0.4.0 and restart')
    expect(html).toContain('>Update<')
    expect(html).not.toContain('href=')
    expect(updateControl(state('available')).command).toBe('update_install')
  })
  it('shows actual download progress and disables repeated installation', () => {
    const html = render(state('downloading', {percent: 42}))
    expect(html).toContain('role="progressbar"')
    expect(html).toContain('aria-valuenow="42"')
    expect(html).toContain('42%')
    expect(updateControl(state('downloading')).busy).toBe(true)
  })
  it('labels download retries and check retries as distinct actions', () => {
    expect(updateControl(state('error', {retry: 'install'})).command).toBe('update_install')
    expect(updateControl(state('error', {retry: 'check'})).command).toBe('update_check')
    expect(render(state('error', {retry: 'install'}))).toContain('>Retry<')
  })
  it.each(['checking', 'ready', 'installing'] as const)('disables %s controls while native work is in progress', phase => {
    expect(updateControl(state(phase)).busy).toBe(true)
    expect(render(state(phase))).toContain('aria-disabled="true"')
  })
  it('does not advertise fake updates in the browser or development app', () => {
    expect(render(state('unsupported'))).not.toContain('Peaks updates')
    expect(render(state('unsupported'))).not.toContain('<button')
  })
})
