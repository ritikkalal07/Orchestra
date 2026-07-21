import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

// https://vitejs.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const apiTarget = env.VITE_API_URL || 'http://localhost:8000'

  return {
    plugins: [react()],
    server: {
      port: 5173,
      proxy: {
        // In dev, proxy /v1 and /ws to the local API server
        '/v1': {
          target: apiTarget,
          changeOrigin: true,
          ws: true,
        },
        '/health': {
          target: apiTarget,
          changeOrigin: true,
        },
      },
    },
    define: {
      // Make VITE_API_URL available at runtime via import.meta.env
      __API_URL__: JSON.stringify(env.VITE_API_URL || ''),
    },
  }
})
