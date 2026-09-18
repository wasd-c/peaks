import {renderToStaticMarkup} from 'react-dom/server'
import {LayerProvider} from '@astryxdesign/core/Layer'
import {afterEach, describe, expect, it} from 'vitest'
import {DiscordPresenceSettings} from './DiscordPresenceSettings'
import {i18n} from '../i18n'

afterEach(() => { void i18n.changeLanguage('en') })

describe('Discord sharing preference', () => {
  it.each([['en', 'Share Discord activity'], ['fr', 'Partage de l’activité Discord'], ['ko', 'Discord 활동 공유']])('exposes one localized sharing toggle in %s without developer configuration', (language, label) => {
    void i18n.changeLanguage(language)
    const html = renderToStaticMarkup(<LayerProvider><DiscordPresenceSettings header={null} /></LayerProvider>)
    expect(html).toContain(label)
    expect(html.match(/role="switch"/g)).toHaveLength(1)
    expect(html).not.toContain('Application ID')
    expect(html).not.toContain('Developer Portal')
    expect(html).not.toContain('Save Discord')
    expect(html).not.toContain('type="text"')
  })
})
