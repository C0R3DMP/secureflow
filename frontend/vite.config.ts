import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  base: '/ui/',
  plugins: [react()],
  server: {
    port: 3000,
    proxy: {
      '/stream': {
        target: 'http://localhost:5000',
        changeOrigin: true,
        ws: true,
      },
      '/api': {
        target: 'http://localhost:5000',
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: '../secureflow/static/dist',
    emptyOutDir: true,
  },
})
