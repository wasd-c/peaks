import React from 'react'
import ReactDOM from 'react-dom/client'
import {LayerProvider} from '@astryxdesign/core/Layer'
import {Theme} from '@astryxdesign/core/theme'
import { App } from './App'
import {peaksTheme} from './theme/peaks'
import {initializeLanguage} from './i18n'
import {LocaleProvider} from './i18n/LocaleProvider'
import '@astryxdesign/core/reset.css'
import '@astryxdesign/core/astryx.css'
import './theme/peaks.css'
import './styles.css'
import './workspace.css'
import './detailSurfaces.css'
import './playerMatchCards.css'
import './utilitySurfaces.css'
import './dialogSurfaces.css'

initializeLanguage()

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <Theme theme={peaksTheme} mode="dark">
      <LocaleProvider>
        <LayerProvider>
          <App />
        </LayerProvider>
      </LocaleProvider>
    </Theme>
  </React.StrictMode>,
)
