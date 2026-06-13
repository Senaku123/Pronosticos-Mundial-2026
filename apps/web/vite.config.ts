import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// In dev the UI calls `/api/*` and Vite proxies to the FastAPI backend (no CORS needed).
// Override the backend with VITE_PROXY_TARGET; in production point VITE_API_BASE at the API.
const target = process.env.VITE_PROXY_TARGET ?? 'http://127.0.0.1:8000'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': {
        target,
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
})
