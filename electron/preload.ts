import { contextBridge, ipcRenderer, type IpcRendererEvent } from 'electron'

contextBridge.exposeInMainWorld('peaks', {
  invoke: (command: string, payload: unknown = {}) => ipcRenderer.invoke('peaks:invoke', command, payload),
  // Taskbar shortcuts ask the renderer to run its usual connection flow, without focusing Peaks.
  onConnectAccount: (listener: (accountId: string) => void) => {
    const handler = (_event: IpcRendererEvent, accountId: unknown) => { if (typeof accountId === 'string') listener(accountId) }
    ipcRenderer.on('peaks:connect-account', handler)
    return () => { ipcRenderer.removeListener('peaks:connect-account', handler) }
  },
})
