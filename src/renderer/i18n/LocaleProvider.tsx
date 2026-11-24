import {type ReactNode} from 'react'
import {ConfigProvider} from 'antd'
import enUS from 'antd/locale/en_US'
import frFR from 'antd/locale/fr_FR'
import koKR from 'antd/locale/ko_KR'
import {useLocale} from './index'

const locales = {en: enUS, fr: frFR, ko: koKR}

/** Ant Design's own strings (pickers, empty states, pagination) follow the app language. */
export function LocaleProvider({children}: {children: ReactNode}) {
  const language = useLocale()
  return <ConfigProvider locale={locales[language]}>{children}</ConfigProvider>
}
