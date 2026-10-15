import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { RouterProvider } from 'react-router/dom';
import { z } from 'zod';

// Self-hosted IBM Plex (SIL OFL 1.1). unicode-range subsets load only what a page uses.
import '@fontsource/ibm-plex-sans/400.css';
import '@fontsource/ibm-plex-sans/500.css';
import '@fontsource/ibm-plex-sans/600.css';
import '@fontsource/ibm-plex-sans-arabic/400.css';
import '@fontsource/ibm-plex-sans-arabic/500.css';
import '@fontsource/ibm-plex-sans-arabic/600.css';

import { installClientErrorReporting } from '@/api/monitoring';
import { router } from '@/app/router';
import '@/i18n';
import './index.css';

// The Content-Security-Policy forbids evaluating strings as code; without this, zod
// probes with Function('') on first use and the browser logs a CSP violation.
z.config({ jitless: true });

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { staleTime: 5 * 60 * 1000, retry: 1, refetchOnWindowFocus: false },
  },
});

installClientErrorReporting();

const container = document.getElementById('root');
if (!container) throw new Error('Root element #root not found');

createRoot(container).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  </StrictMode>,
);
