import { fileURLToPath, URL } from 'node:url';

import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

// /api is proxied to the FastAPI service so the browser talks to one origin and the
// SameSite=Strict session cookie works without cross-origin credentials.
const apiTarget = process.env.OSRIP_API_ORIGIN ?? 'http://127.0.0.1:8010';

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
  // MapLibre starts its worker as a module worker.
  worker: { format: 'es' },
  server: {
    // OSRIP_WEB_PORT (test configs), then PORT (assigned by the preview launcher), then 5173.
    port: Number(process.env.OSRIP_WEB_PORT ?? process.env.PORT ?? 5173),
    strictPort: true,
    proxy: {
      '/api': {
        target: apiTarget,
        changeOrigin: false,
        // The API is not running or refused the connection: answer as the API would, so the page
        // says the server is unavailable (in the reader's language) instead of a bare 502.
        configure: (proxy) => {
          proxy.on('error', (_error, _request, response) => {
            if (!('writeHead' in response) || response.headersSent || response.writableEnded) return;
            response.writeHead(503, { 'Content-Type': 'application/json' });
            response.end(JSON.stringify({
              error: { code: 'server_unavailable', message: `The OSRIP API is not reachable at ${apiTarget}.` },
            }));
          });
        },
      },
    },
  },
});
