import {type ReactNode} from 'react'
import {InternationalizationProvider} from '@astryxdesign/core/i18n'
import frFR from '@astryxdesign/core/locales/fr-FR.json'
import koKR from '@astryxdesign/core/locales/ko-KR.json'
import {localeTags, useLocale} from './index'

const messages = {'fr-FR': frFR, 'ko-KR': koKR}

export function LocaleProvider({children}: {children: ReactNode}) {
  const language = useLocale()
  return <InternationalizationProvider locale={localeTags[language]} messages={messages}>{children}</InternationalizationProvider>
}
