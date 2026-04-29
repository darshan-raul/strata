import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: 3000,
    proxy: {
      '/application': {
        target: 'http://authentik-server:9000',
        changeOrigin: true,
      },
      '/if': {
        target: 'http://authentik-server:9000',
        changeOrigin: true,
      },
      '/api': {
        target: 'http://authentik-server:9000',
        changeOrigin: true,
      },
      '/static/dist': {
        target: 'http://authentik-server:9000',
        changeOrigin: true,
      },
      '/media': {
        target: 'http://authentik-server:9000',
        changeOrigin: true,
      },
    },
  },
})
