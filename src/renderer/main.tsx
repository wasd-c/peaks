import React from 'react'
import ReactDOM from 'react-dom/client'
import {PeaksProvider} from './ui'
import { App } from './App'
import {initializeLanguage} from './i18n'
import {LocaleProvider} from './i18n/LocaleProvider'
import './theme/tokens.css'
import './ui/ui.css'
import './styles.css'
import './workspace.css'
import './detailSurfaces.css'
import './playerMatchCards.css'
import './utilitySurfaces.css'
import './dialogSurfaces.css'
import './accountPicker.css'

initializeLanguage()

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <PeaksProvider>
      <LocaleProvider>
        <App />
      </LocaleProvider>
    </PeaksProvider>
  </React.StrictMode>,
)
