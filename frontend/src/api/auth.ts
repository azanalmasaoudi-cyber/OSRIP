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
  has_recovery_code: z.boolean().nullable().optional(),
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

// ------------------------------------------------------------------ username accounts

/** A new session and the recovery code, shown once (never stored in the browser). */
const withRecovery = z.object({ status: z.string(), recovery_code: z.string(), me: meSchema });

export function useRegisterUsername() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: { username: string; password: string; password_confirm: string }) =>
      apiJson('/auth/register/username', withRecovery, jsonBody('POST', body)),
    onSuccess: (r) => client.setQueryData(ME_KEY, r.me),
  });
}

/** A forgotten password: username, recovery code and a new password. */
export function useRecover() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: { username: string; recovery_code: string; new_password: string; new_password_confirm: string }) =>
      apiJson('/auth/recover', withRecovery, jsonBody('POST', body)),
    onSuccess: (r) => client.setQueryData(ME_KEY, r.me),
  });
}

export function useNewRecoveryCode() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (currentPassword: string) =>
      apiJson('/auth/recovery-code', z.object({ recovery_code: z.string() }), jsonBody('POST', { current_password: currentPassword })),
    onSuccess: () => void client.invalidateQueries({ queryKey: ME_KEY }),
  });
}

/** An administrator's reset: a temporary password, returned once, that must be changed. */
export function useAdminResetPassword() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (userId: string) =>
      apiJson(`/admin/users/${userId}/reset-password`, z.object({ temporary_password: z.string() }), jsonBody('POST', {})),
    onSettled: () => void client.invalidateQueries({ queryKey: ['admin', 'users'] }),
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
    // sandbox: real WhatsApp messages from Meta's test sender, to approved test numbers only.
    status: z.enum(['disabled', 'not_configured', 'test', 'sandbox', 'configured']),
    channel: z.enum(['sms', 'whatsapp']).default('sms'),
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

/** The page's language: account e-mails and SMS codes are sent in it first (both languages
 * are always in an e-mail). */
function pageLanguage(): 'en' | 'ar' {
  return document.documentElement.lang === 'ar' ? 'ar' : 'en';
}

export function useRegister() {
  return useMutation({
    mutationFn: (body: { email: string; display_name: string; password: string }) =>
      apiJson('/auth/register', accepted, jsonBody('POST', { ...body, language: pageLanguage() })),
  });
}

export function useEmailRequest(path: '/auth/password/forgot' | '/auth/magic-link' | '/auth/verify-email/resend') {
  return useMutation({ mutationFn: (email: string) => apiJson(path, accepted, jsonBody('POST', { email, language: pageLanguage() })) });
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
    // password: needed to replace a verified number on an account that has one.
    mutationFn: (body: { country_code: string; number: string; purpose: 'sign_in' | 'link'; password?: string }) =>
      apiJson('/auth/phone/request', challengeSchema, jsonBody('POST', { ...body, language: pageLanguage() })),
  });
}

const verifiedSchema = z.object({ status: z.enum(['registered', 'signed_in', 'linked', 'changed']), me: meSchema });
export type PhoneOutcome = z.infer<typeof verifiedSchema>['status'];

export function usePhoneVerify() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: { challenge_id: string; code: string; display_name?: string }) =>
      apiJson('/auth/phone/verify', verifiedSchema, jsonBody('POST', { ...body, language: pageLanguage() })),
    onSuccess: (result) => {
      client.setQueryData(ME_KEY, result.me);
      void client.invalidateQueries({ queryKey: ['imports'] });
    },
  });
}

/** Add an e-mail address, or change a confirmed one (password needed for accounts that have one). */
export function useLinkEmail() {
  return useMutation({
    mutationFn: (vars: { email: string; password?: string }) =>
      apiJson('/auth/email/link', accepted, jsonBody('POST', { ...vars, language: pageLanguage() })),
  });
}

export function useConfirmEmailLink() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (token: string) => apiJson('/auth/email/link/confirm', accepted, jsonBody('POST', { token, language: pageLanguage() })),
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

// ------------------------------------------------------------------ roles and groups (migration 0026)

const permissionRow = z.object({ code: z.string(), description: z.string() });
const roleRow = z.object({
  code: z.string(),
  description: z.string(),
  builtin: z.boolean(),
  permissions: z.array(z.string()),
  users: z.number(),
  groups: z.number(),
});
export type AccessRole = z.infer<typeof roleRow>;
const groupRow = z.object({
  id: z.string(),
  name: z.string(),
  description: z.string(),
  roles: z.array(z.string()),
  permissions: z.array(z.string()),
  members: z.array(z.object({
    id: z.string(), display_name: z.string(), username: z.string().nullable(), email: z.string().nullable(),
  })),
});
export type AccessGroup = z.infer<typeof groupRow>;
const ACCESS_KEY = ['admin', 'access'] as const;

export function useAdminPermissions(enabled: boolean) {
  return useQuery({ queryKey: [...ACCESS_KEY, 'permissions'], queryFn: () => apiJson('/admin/permissions', z.array(permissionRow)), enabled });
}

export function useAdminRoles(enabled: boolean) {
  return useQuery({ queryKey: [...ACCESS_KEY, 'roles'], queryFn: () => apiJson('/admin/roles', z.array(roleRow)), enabled });
}

export function useAdminGroups(enabled: boolean) {
  return useQuery({ queryKey: [...ACCESS_KEY, 'groups'], queryFn: () => apiJson('/admin/groups', z.array(groupRow)), enabled });
}

/** Create, change or remove a custom role; the list is reloaded afterwards. */
export function useSaveRole() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (v: { code: string; description: string; permissions: string[]; mode: 'create' | 'update' | 'delete' }) =>
      v.mode === 'create'
        ? apiJson('/admin/roles', z.array(roleRow), jsonBody('POST', { code: v.code, description: v.description, permissions: v.permissions }))
        : v.mode === 'update'
          ? apiJson(`/admin/roles/${v.code}`, z.array(roleRow), jsonBody('PUT', { description: v.description, permissions: v.permissions }))
          : apiJson(`/admin/roles/${v.code}`, z.array(roleRow), { method: 'DELETE' }),
    onSettled: () => {
      void client.invalidateQueries({ queryKey: ACCESS_KEY });
      void client.invalidateQueries({ queryKey: ['admin', 'users'] });
    },
  });
}

/** Create, change or remove a group (its name, description, roles and permissions). */
export function useSaveGroup() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (v: { id?: string; name: string; description: string; roles: string[]; permissions: string[]; mode: 'create' | 'update' | 'delete' }) => {
      const body = { name: v.name, description: v.description, roles: v.roles, permissions: v.permissions };
      if (v.mode === 'create') return apiJson('/admin/groups', groupRow, jsonBody('POST', body));
      if (v.mode === 'update') return apiJson(`/admin/groups/${v.id}`, groupRow, jsonBody('PUT', body));
      return apiFetch(`/admin/groups/${v.id}`, { method: 'DELETE' }).then(() => null); // 204: no body
    },
    onSettled: () => void client.invalidateQueries({ queryKey: ACCESS_KEY }),
  });
}

export function useGroupMember() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ groupId, userId, add }: { groupId: string; userId: string; add: boolean }) =>
      add
        ? apiJson(`/admin/groups/${groupId}/members`, groupRow, jsonBody('POST', { user_id: userId }))
        : apiJson(`/admin/groups/${groupId}/members/${userId}`, groupRow, { method: 'DELETE' }),
    onSettled: () => void client.invalidateQueries({ queryKey: ACCESS_KEY }),
  });
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
