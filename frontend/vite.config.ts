import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      // Forwarded to the FastAPI backend (see api/main.py) during `npm run dev`.
      // In production, api/main.py serves the built frontend itself, so both
      // sides are same-origin and this proxy is dev-only.
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
})
