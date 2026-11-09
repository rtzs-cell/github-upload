import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const apiHost = process.env.RADAR_API_HOST === '0.0.0.0'
  ? '127.0.0.1'
  : (process.env.RADAR_API_HOST ?? '127.0.0.1')
const apiPort = process.env.RADAR_API_PORT ?? '8000'
const apiProxyTarget = process.env.RADAR_API_PROXY_TARGET ?? `http://${apiHost}:${apiPort}`

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: false,
    proxy: {
      '/api': {
        target: apiProxyTarget,
        changeOrigin: true,
      },
    },
  },
})
