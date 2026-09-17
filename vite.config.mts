import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  base: './',
  publicDir: false,
  server: {
    watch: {
      // Packaging and local captures can generate large trees while Vite runs.
      // None of these directories is renderer source.
      ignored: ['**/artifacts/**', '**/build/**', '**/release/**', '**/dist/**', '**/dist-electron/**', '**/.venv/**', '**/.pytest_cache/**', '**/.mypy_cache/**', '**/.ruff_cache/**'],
    },
  },
  build: {outDir: 'dist'},
})
