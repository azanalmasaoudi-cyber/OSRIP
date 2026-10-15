import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { z } from 'zod';

import { apiFetch, apiJson, jsonBody } from './client';
import { adapterKind, apiBaseUrl } from './config';

const meSchema = z.object({
  authenticated: z.boolean(),
  user_id: z.string().nullable().optional(),
  email: z.string().nullable().optional(),
  display_name: z.string().nullable().optional(),
  email_verified: z.boolean().nullable().optional(),
  phone: z.string().nullable().optional(),
  phone_verified: z.boolean().nullable().optional(),
  has_password: z.boolean().nullable().optional(),
  username: z.string().nullable().optional(),
  // A temporary password must be replaced before the account can do anything else.
  password_change_required: z.boolean().optional(),
  roles: z.array(z.string()),
  permissions: z.array(z.string()),
});
export type Me = z.infer<typeof meSchema>;

export const ANONYMOUS: Me = { authenticated: false, roles: [], permissions: [] };
const ME_KEY = ['auth', 'me'] as const;

/**
 * Who is signed in. Permissions here only decide what the interface offers;
 * the server checks every request independently.
 */
export function useMe() {
  return useQuery({
    queryKey: ME_KEY,
    queryFn: () => apiJson('/auth/me', meSchema),
    enabled: adapterKind === 'http',
    staleTime: 60_000,
    retry: false,
  });
}

export function hasPermission(me: Me | undefined, permission: string): boolean {
  return Boolean(me?.permissions.includes(permission));
}

export function useLogin() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (credentials: { email: string; password: string }) =>
      apiJson('/auth/login', meSchema, jsonBody('POST', credentials)),
    onSuccess: (me) => {
      client.setQueryData(ME_KEY, me);
      void client.invalidateQueries({ queryKey: ['imports'] });
    },
  });
}

export function useChangePassword() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: { current_password: string; new_password: string }) =>
      apiJson('/auth/password/change', meSchema, jsonBody('POST', body)),
    onSuccess: (me) => {
      client.setQueryData(ME_KEY, me);
      void client.invalidateQueries({ queryKey: ['assistant'] });
    },
  });
}

export function useLogout() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => apiFetch('/auth/logout', { method: 'POST' }),
    onSettled: () => {
      client.setQueryData(ME_KEY, ANONYMOUS);
      client.removeQueries({ queryKey: ['imports'] });
      client.removeQueries({ queryKey: ['assistant'] });
    },
  });
}

// ------------------------------------------------------------------ sign-in methods

const providersSchema = z.object({
  password: z.boolean(),
  registration: z.boolean(),
  magic_link: z.boolean(),
  email_delivery: z.enum(['smtp', 'outbox', 'disabled']),
  oidc: z.object({ google: z.boolean(), microsoft: z.boolean() }),
  sms: z.object({
    available: z.boolean(),
    status: z.enum(['disabled', 'not_configured', 'test', 'configured']),
    provider: z.string().nullable(),
    note: z.string().nullable(),
    default_country: z.string(),
    resend_seconds: z.number(),
    code_minutes: z.number(),
  }),
  country_codes: z.array(z.string()),
});
export type Providers = z.infer<typeof providersSchema>;
export const OIDC_PROVIDERS = ['google', 'microsoft'] as const;
export type OidcProvider = (typeof OIDC_PROVIDERS)[number];

export function useProviders() {
  return useQuery({
    queryKey: ['auth', 'providers'],
    queryFn: () => apiJson('/auth/providers', providersSchema),
    enabled: adapterKind === 'http',
    staleTime: 5 * 60_000,
  });
}

/** Full-page navigation to the backend, which redirects to the provider. */
export function oidcStartUrl(provider: OidcProvider, intent: 'sign_in' | 'link' = 'sign_in'): string {
  return `${apiBaseUrl}/auth/oidc/${provider}/start?intent=${intent}`;
}

const accepted = z.object({ status: z.string(), message: z.string().optional() });

export function useRegister() {
  return useMutation({
    mutationFn: (body: { email: string; display_name: string; password: string }) =>
      apiJson('/auth/register', accepted, jsonBody('POST', body)),
  });
}

export function useEmailRequest(path: '/auth/password/forgot' | '/auth/magic-link' | '/auth/verify-email/resend') {
  return useMutation({ mutationFn: (email: string) => apiJson(path, accepted, jsonBody('POST', { email })) });
}

export function useVerifyEmail() {
  return useMutation({ mutationFn: (token: string) => apiJson('/auth/verify-email', accepted, jsonBody('POST', { token })) });
}

export function useResetPassword() {
  return useMutation({
    mutationFn: (body: { token: string; password: string }) => apiJson('/auth/password/reset', accepted, jsonBody('POST', body)),
  });
}

export function useConsumeMagicLink() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (token: string) => apiJson('/auth/magic-link/consume', meSchema, jsonBody('POST', { token })),
    onSuccess: (me) => client.setQueryData(ME_KEY, me),
  });
}

const identitySchema = z.object({
  id: z.string(),
  provider: z.enum(OIDC_PROVIDERS),
  email: z.string().nullable(),
  linked_at: z.string(),
  last_used_at: z.string().nullable(),
});

export function useIdentities(enabled: boolean) {
  return useQuery({
    queryKey: ['auth', 'identities'],
    queryFn: () => apiJson('/auth/identities', z.array(identitySchema)),
    enabled: adapterKind === 'http' && enabled,
  });
}

export function useUnlinkIdentity() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => apiFetch(`/auth/identities/${id}`, { method: 'DELETE' }),
    onSettled: () => void client.invalidateQueries({ queryKey: ['auth', 'identities'] }),
  });
}

// ------------------------------------------------------------------ phone (SMS verification)

const challengeSchema = z.object({
  challenge_id: z.string(),
  phone_masked: z.string(),
  expires_in: z.number(),
  resend_after: z.number(),
  max_attempts: z.number(),
});
export type PhoneChallenge = z.infer<typeof challengeSchema>;

export function usePhoneRequest() {
  return useMutation({
    mutationFn: (body: { country_code: string; number: string; purpose: 'sign_in' | 'link' }) =>
      apiJson('/auth/phone/request', challengeSchema, jsonBody('POST', body)),
  });
}

const verifiedSchema = z.object({ status: z.enum(['registered', 'signed_in', 'linked']), me: meSchema });

export function usePhoneVerify() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: { challenge_id: string; code: string; display_name?: string }) =>
      apiJson('/auth/phone/verify', verifiedSchema, jsonBody('POST', body)),
    onSuccess: (result) => {
      client.setQueryData(ME_KEY, result.me);
      void client.invalidateQueries({ queryKey: ['imports'] });
    },
  });
}

export function useLinkEmail() {
  return useMutation({ mutationFn: (email: string) => apiJson('/auth/email/link', accepted, jsonBody('POST', { email })) });
}

export function useConfirmEmailLink() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (token: string) => apiJson('/auth/email/link/confirm', accepted, jsonBody('POST', { token })),
    onSuccess: () => void client.invalidateQueries({ queryKey: ME_KEY }),
  });
}

const smsMessage = z.object({ to: z.string(), code: z.string(), sent_at: z.number() });

/** Development and tests only: codes from the scripted SMS test provider (404 otherwise). */
export function useDevSmsOutbox(enabled: boolean) {
  return useQuery({
    queryKey: ['dev', 'sms-outbox'],
    queryFn: () => apiJson('/dev/sms-outbox', z.array(smsMessage)),
    enabled: adapterKind === 'http' && enabled,
    retry: false,
    refetchInterval: 3000,
  });
}

// ------------------------------------------------------------------ administration

const adminUser = z.object({
  id: z.string(),
  email: z.string().nullable(),
  phone: z.string().nullable().optional(),
  display_name: z.string(),
  status: z.enum(['active', 'suspended']),
  roles: z.array(z.string()),
  grants: z.array(z.string()),
  email_verified: z.boolean(),
  created_via: z.string(),
  username: z.string().nullable().optional(),
});
export type AdminUser = z.infer<typeof adminUser>;
export const ROLES = ['viewer', 'analyst', 'data_manager', 'administrator'] as const;

export function useAdminUsers(enabled: boolean) {
  return useQuery({ queryKey: ['admin', 'users'], queryFn: () => apiJson('/admin/users', z.array(adminUser)), enabled });
}

export function useSetRole() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ userId, role, add }: { userId: string; role: string; add: boolean }) =>
      add
        ? apiJson(`/admin/users/${userId}/roles`, adminUser, jsonBody('POST', { role }))
        : apiJson(`/admin/users/${userId}/roles/${role}`, adminUser, { method: 'DELETE' }),
    onSettled: () => void client.invalidateQueries({ queryKey: ['admin', 'users'] }),
  });
}

const outboxMessage = z.object({
  id: z.number(), to: z.string(), subject: z.string(), body: z.string(), purpose: z.string(), created_at: z.string(),
});
export type OutboxMessage = z.infer<typeof outboxMessage>;

export function useDevOutbox() {
  return useQuery({
    queryKey: ['dev', 'outbox'],
    queryFn: () => apiJson('/dev/outbox', z.array(outboxMessage)),
    enabled: adapterKind === 'http',
    retry: false,
    refetchInterval: 5000,
  });
}
