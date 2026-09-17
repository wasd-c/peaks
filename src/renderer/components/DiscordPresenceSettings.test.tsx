import {renderToStaticMarkup} from 'react-dom/server'
import {LayerProvider} from '@astryxdesign/core/Layer'
import {describe, expect, it} from 'vitest'
import {DiscordPresenceSettings} from './DiscordPresenceSettings'

describe('Discord sharing preference', () => {
  it('exposes a single sharing toggle without developer configuration', () => {
    const html = renderToStaticMarkup(<LayerProvider><DiscordPresenceSettings header={null} /></LayerProvider>)
    expect(html).toContain('Partage de l’activité Discord')
    expect(html.match(/role="switch"/g)).toHaveLength(1)
    expect(html).not.toContain('Application ID')
    expect(html).not.toContain('Developer Portal')
    expect(html).not.toContain('Save Discord')
    expect(html).not.toContain('type="text"')
  })
})
