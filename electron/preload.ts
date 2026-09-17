import { contextBridge, ipcRenderer } from 'electron'

contextBridge.exposeInMainWorld('peaks', { invoke: (command: string, payload: unknown = {}) => ipcRenderer.invoke('peaks:invoke', command, payload) })
