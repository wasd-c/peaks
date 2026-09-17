import React from 'react'
import ReactDOM from 'react-dom/client'
import {LayerProvider} from '@astryxdesign/core/Layer'
import {Theme} from '@astryxdesign/core/theme'
import { App } from './App'
import {peaksTheme} from './theme/peaks'
import '@astryxdesign/core/reset.css'
import '@astryxdesign/core/astryx.css'
import './theme/peaks.css'
import './styles.css'
import './workspace.css'
import './detailSurfaces.css'
import './playerMatchCards.css'
import './utilitySurfaces.css'
import './dialogSurfaces.css'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <Theme theme={peaksTheme} mode="dark">
      <LayerProvider>
        <App />
      </LayerProvider>
    </Theme>
  </React.StrictMode>,
)
