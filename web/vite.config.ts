import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  // A playbook view's source sits outside web/, where Node resolution finds
  // no node_modules. Resolve React from here instead — which is also the rule
  // the view depends on at runtime: one React instance, never two.
  resolve: {
    dedupe: ['react', 'react-dom', 'react/jsx-runtime', 'react/jsx-dev-runtime'],
  },
  server: {
    // Default is the workspace root, which web/package-lock.json pins to web/ —
    // so a test importing the built playbook view under ../playbooks is Denied.
    // Widened by exactly one directory, not to the whole repo.
    fs: { allow: ['.', '../playbooks'] },
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
