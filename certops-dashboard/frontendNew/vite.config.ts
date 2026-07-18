import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
import path from 'path';
import {defineConfig} from 'vite';

export default defineConfig(() => {
  return {
    plugins: [react(), tailwindcss()],
    resolve: {
      alias: {
        '@': path.resolve(__dirname, './src'),
      },
    },
    server: {
      // HMR is disabled in AI Studio via DISABLE_HMR env var.
      // Do not modifyâ€”file watching is disabled to prevent flickering during agent edits.
      hmr: process.env.DISABLE_HMR !== 'true',
      // Disable file watching when DISABLE_HMR is true to save CPU during agent edits.
      watch: process.env.DISABLE_HMR === 'true' ? null : {},
      // Proxy /api and /auth requests to the FastAPI backend.
      // The backend runs on port 8000 (see certops-dashboard/src/api.py).
      proxy: {
        '/api': {
          target: process.env.VITE_API_PROXY_TARGET ?? 'http://localhost:8000',
          changeOrigin: true,
          secure: false,
        },
        '/auth': {
          target: process.env.VITE_API_PROXY_TARGET ?? 'http://localhost:8000',
          changeOrigin: true,
          secure: false,
        },
      },
    },
  };
});
