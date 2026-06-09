import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: 3000,
    proxy: {
      '/auth': {
        target: 'http://localhost:8080',
        changeOrigin: true,
      },
      '/catalog': {
        target: 'http://localhost:80',
        changeOrigin: true,
      },
      '/provisioner': {
        target: 'http://localhost:80',
        changeOrigin: true,
      },
      '/scorecard': {
        target: 'http://localhost:80',
        changeOrigin: true,
      },
      '/workflow': {
        target: 'http://localhost:80',
        changeOrigin: true,
      },
      '/audit': {
        target: 'http://localhost:80',
        changeOrigin: true,
      },
    },
  },
})
