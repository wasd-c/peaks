import { configDefaults, defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  base: './',
  publicDir: false,
  test: {
    exclude: [...configDefaults.exclude, '**/artifacts/**'],
  },
  server: {
    watch: {
      // Packaging and local captures can generate large trees while Vite runs.
      // None of these directories is renderer source.
      ignored: ['**/artifacts/**', '**/build/**', '**/release/**', '**/dist/**', '**/dist-electron/**', '**/.venv/**', '**/.pytest_cache/**', '**/.mypy_cache/**', '**/.ruff_cache/**'],
    },
  },
  build: {outDir: 'dist'},
})
