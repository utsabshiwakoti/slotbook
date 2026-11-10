import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// The dev server forwards /api to FastAPI, so the browser sees one origin (no CORS setup locally).
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': process.env.API_URL || 'http://localhost:8000',
    },
  },
})
