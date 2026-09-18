import {Selector} from '@astryxdesign/core/Selector'
import {LANGUAGES, setLanguage, supportedLanguage, t, useLocale} from '../i18n'

export function LanguageSelector({isLabelHidden = false}: {isLabelHidden?: boolean}) {
  const language = useLocale()
  return <Selector label={t('Language')} isLabelHidden={isLabelHidden} size="sm"
    value={language} options={[...LANGUAGES]} onChange={value => {
      const next = supportedLanguage(value)
      if (next) setLanguage(next)
    }} />
}
