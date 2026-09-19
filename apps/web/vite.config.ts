import react from '@vitejs/plugin-react';
import { resolve } from 'node:path';
import { defineConfig } from 'vitest/config';

export default defineConfig({
  plugins: [react()],
  build: {
    sourcemap: false,
    rolldownOptions: { input: { main: resolve(import.meta.dirname, 'index.html'), demo: resolve(import.meta.dirname, 'demo.html') } },
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./tests/setup.ts'],
    clearMocks: true,
    restoreMocks: true,
    unstubGlobals: true,
    css: true,
  },
});
