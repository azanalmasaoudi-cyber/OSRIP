import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { z } from 'zod';

import { apiJson } from './client';
import { adapterKind, apiBaseUrl } from './config';

const integration = z.object({
  configured: z.boolean(),
  status: z.string(),
  last_failure_code: z.string().nullable().optional(),
  failures_since_start: z.number().optional(),
  mode: z.string().optional(),
  provider: z.string().optional(),
  note: z.string().optional(),
});

const usageRow = z.object({
  provider: z.string(), calls: z.number(), failures: z.number(), refused: z.number(),
  input_tokens: z.number(), output_tokens: z.number(),
  estimated_cost_usd: z.number().nullable(), average_ms: z.number().nullable(),
});
export type UsageRow = z.infer<typeof usageRow>;
const usageSchema = z.object({
  windows: z.object({ day: z.array(usageRow), month: z.array(usageRow) }),
  priced: z.array(z.string()),
});
const syncFeedSchema = z.object({
  code: z.string(), title: z.object({ en: z.string(), ar: z.string() }), access: z.string(),
  enabled: z.boolean(), auto_publish: z.boolean(),
  last_checked_at: z.string().nullable(), last_success_at: z.string().nullable(), next_check_at: z.string().nullable(),
  last_status: z.string().nullable(), consecutive_failures: z.number(), awaiting_approval: z.number(),
});
const performanceSchema = z.object({
  window: z.number(), requests: z.number(), uptime_seconds: z.number(),
  p50_ms: z.number().nullable(), p95_ms: z.number().nullable(), max_ms: z.number().nullable(),
  server_errors: z.number(),
  slowest: z.array(z.object({ route: z.string(), requests: z.number(), p95_ms: z.number() })),
});

const monitoringSchema = z.object({
  ready: z.boolean(),
  release: z.string(),
  checks: z.record(z.string(), z.string().nullable()),
  integrations: z.record(z.string(), integration),
  errors: z.array(z.object({
    fingerprint: z.string(), source: z.string(), kind: z.string(), message: z.string(),
    location: z.string().nullable(), count: z.number(), last_seen: z.string(), last_request_id: z.string().nullable(),
  })),
  usage: usageSchema,
  sync: z.array(syncFeedSchema),
  performance: performanceSchema,
});
export type Monitoring = z.infer<typeof monitoringSchema>;

export function useMonitoring(enabled: boolean) {
  return useQuery({
    queryKey: ['admin', 'monitoring'],
    queryFn: () => apiJson('/admin/monitoring', monitoringSchema),
    enabled: adapterKind === 'http' && enabled,
    refetchInterval: 30_000,
  });
}

// ------------------------------------------------------------------ AI and search providers

const callSchema = z.object({
  status: z.string(), capability: z.string(), model: z.string().nullable().optional(), at: z.string(),
  duration_ms: z.number().optional(),
});
const providerSchema = z.object({
  provider: z.enum(['anthropic', 'openai', 'gemini', 'deepseek', 'brave', 'firecrawl']),
  label: z.string(),
  docs: z.string(),
  billing: z.enum(['usage_billed', 'free_tier_available', 'plan', 'credits']).optional(),
  roles: z.array(z.string()),
  in_use: z.boolean(),
  capabilities: z.record(z.string(), z.object({
    missing: z.array(z.string()), model: z.string().nullable().optional(), chosen: z.boolean(),
  })),
  configured: z.boolean(),
  status: z.enum(['unavailable', 'configured', 'tested', 'failed']),
  last_test: callSchema.nullable().optional(),
  last_call: callSchema.nullable().optional(),
  today: z.object({ calls: z.number(), errors: z.number(), estimated_cost_usd: z.number().nullable() }),
  limits: z.object({
    daily_calls: z.number(), daily_budget_usd: z.number().nullable(), prices_configured: z.boolean(),
  }),
});
export type ProviderState = z.infer<typeof providerSchema>;
const readinessSchema = z.object({
  providers: z.array(providerSchema),
  routing: z.object({
    answer: z.object({ primary: z.string().nullable(), fallback: z.string().nullable() }),
    search: z.object({ primary: z.string().nullable(), fallback: z.string().nullable() }),
  }),
  policy: z.object({ en: z.string(), ar: z.string() }),
});

/** Provider readiness: configured, tested, unavailable or failed (setting names, never values). */
export function useProviderReadiness(enabled: boolean) {
  return useQuery({
    queryKey: ['admin', 'providers'],
    queryFn: () => apiJson('/admin/providers', readinessSchema),
    enabled: adapterKind === 'http' && enabled,
  });
}

/** One minimal live call to a provider (an administrator's action; it may cost a little). */
export function useTestProvider() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ provider, capability }: { provider: string; capability: string }) =>
      apiJson(`/admin/providers/${provider}/test?capability=${capability}`,
        z.object({ provider: z.string(), capability: z.string(), status: z.string() }).passthrough(), { method: 'POST' }),
    onSettled: () => void client.invalidateQueries({ queryKey: ['admin', 'providers'] }),
  });
}

let sent = 0;
const SESSION_LIMIT = 10;

/** Report a browser error (no cookies, no personal data, query strings removed server-side). */
export function reportClientError(kind: string, message: string): void {
  if (adapterKind !== 'http' || sent >= SESSION_LIMIT) return;
  sent += 1;
  const body = JSON.stringify({
    kind: kind.slice(0, 120) || 'Error',
    message: (message || 'Unknown error').slice(0, 2000),
    location: window.location.origin + window.location.pathname,
  });
  void fetch(`${apiBaseUrl}/telemetry/client-errors`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body, credentials: 'omit', keepalive: true,
  }).catch(() => undefined);
}

export function installClientErrorReporting(): void {
  window.addEventListener('error', (event) => {
    const error: unknown = event.error;
    reportClientError(error instanceof Error ? error.name : 'Error', event.message);
  });
  window.addEventListener('unhandledrejection', (event) => {
    const reason: unknown = event.reason;
    reportClientError(reason instanceof Error ? reason.name : 'UnhandledRejection', reason instanceof Error ? reason.message : String(reason));
  });
}
