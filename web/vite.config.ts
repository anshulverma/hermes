import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8080',
        changeOrigin: true,
      },
    },
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: './src/test/setup.ts',
    // tests-ui/ belongs to Playwright: those specs drive a real browser and
    // would fail under jsdom, which has no layout engine.
    exclude: ['node_modules/**', 'dist/**', 'tests-ui/**'],
  },
})
