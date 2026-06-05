import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
        '/api': {
        target: 'http://127.0.0.1:8002',
        changeOrigin: true,
      },
      '/projects': {
        target: 'http://127.0.0.1:8002',
        changeOrigin: true,
      },
      '/scripts': {
        target: 'http://127.0.0.1:8002',
        changeOrigin: true,
      },
      '/jobs': {
        target: 'http://127.0.0.1:8002',
        changeOrigin: true,
      },
      '/uploads': {
        target: 'http://127.0.0.1:8002',
        changeOrigin: true,
      },
      '/settings': {
        target: 'http://127.0.0.1:8002',
        changeOrigin: true,
      }
    }
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
  }
})
