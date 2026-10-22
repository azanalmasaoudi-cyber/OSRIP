import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { z } from 'zod';

import { apiFetch, apiJson, jsonBody } from './client';
import { adapterKind } from './config';
import type { DataMode } from '@/domain/types';

/** The evidence-grounded assistant. All model calls and credentials stay on the server. */

const bilingual = z.object({ en: z.string(), ar: z.string() });

const evidenceSchema = z.object({
  id: z.string(),
  kind: z.string(),
  indicator: z.string().optional(),
  indicator_name: bilingual.optional(),
  area: z.string().optional(),
  area_name: bilingual.optional(),
  frequency: z.string().optional(),
  period_start: z.string().optional(),
  period_end: z.string().optional(),
  period_complete: z.boolean().optional(),
  value: z.string().nullable().optional(),
  unit: z.string().nullable().optional(),
  unit_label: bilingual.optional(),
  data_mode: z.string().optional(),
  dataset_version: z.string().optional(),
  source: z.object({
    title: z.string(),
    publisher: z.string().nullable(),
    url: z.string().nullable(),
    access_date: z.string().nullable(),
    reference_period: z.string().nullable(),
    source_code: z.string().nullable().optional(),
    locator: z.string().nullable().optional(),
  }).optional(),
  // observed | calculated | forecast | hypothetical | reference
  evidence_class: z.string().optional(),
  period_kind: z.string().optional(),
  value_operator: z.string().nullable().optional(),
  revision_status: z.string().nullable().optional(),
  record_ref: z.string().nullable().optional(),
  name: bilingual.optional(),
  definition: bilingual.optional(),
  limitation: bilingual.optional(),
  // Web evidence (kind 'web'), search attempts (kind 'search') and documented notes
  // (kind 'note', with a bilingual title).
  title: z.union([z.string(), bilingual]).optional(),
  url: z.string().optional(),
  host: z.string().optional(),
  publisher: z.union([bilingual, z.string()]).optional(),
  source_class: z.enum(['official', 'international', 'research', 'secondary']).optional(),
  content_kind: z.string().optional(),
  published: z.string().nullable().optional(),
  published_basis: z.string().nullable().optional(),
  retrieved_at: z.string().optional(),
  text: z.string().optional(),
  text_ar: z.string().optional(),
  query: z.string().optional(),
  queries: z.array(z.object({ query: z.string(), language: z.string() })).optional(),
  provider: z.string().nullable().optional(),
  result_count: z.number().optional(),
  error: z.string().optional(),
  // Web evidence: may it be out of date, where the quoted text is, and the document digest.
  freshness: z.enum(['current', 'stale', 'undated']).optional(),
  locator: z.string().optional(),
  content_sha256: z.string().optional(),
  // Which of these it is: approved official observation, synthetic demonstration, unreviewed
  // external evidence, OSRIP calculation, model forecast, assumption-based scenario, reference.
  data_status: z.string().optional(),
  // A provider summary: the AI provider (model) whose cited statement this is.
  summary_by: z.string().nullable().optional(),
  role: z.string().optional(),
}).passthrough();
export type Evidence = z.infer<typeof evidenceSchema>;

const calculationSchema = z.object({
  id: z.string(),
  kind: z.string(),
  calculation: z.string(),
  formula: bilingual,
  inputs: z.array(z.string()).optional(),
  status: z.string().optional(),
  value: z.string().nullable().optional(),
  unit: z.string().nullable().optional(),
  reason: z.object({ code: z.string(), en: z.string(), ar: z.string() }).nullable().optional(),
});
export type AssistantCalculation = z.infer<typeof calculationSchema>;

// 'profile': a greeting or identity reply from Al Mulhim's approved profile (not AI-generated,
// never charged); 'cancelled': the user stopped the question before it was answered;
// 'data_report': the answer service failed, so the reply lists published records and OSRIP
// calculations without AI interpretation (never charged, can be retried).
export const MESSAGE_STATUSES = [
  'answered', 'clarification', 'no_evidence', 'unverified', 'unavailable', 'lookup', 'profile', 'cancelled',
  'data_report',
] as const;

/** Ask: a direct answer. Analyze: calculations and recommendation cards. Research: web and
 * documents, Arabic and English. Compare: areas or periods side by side. Scenario: what-if
 * arithmetic on stated assumptions, kept apart from forecasts. */
export const ASSISTANT_MODES = ['ask', 'analyze', 'research', 'compare', 'scenario'] as const;
export type AssistantMode = (typeof ASSISTANT_MODES)[number];

export const DRIVERS = [
  'weather', 'population', 'industrial_activity', 'desalination', 'renewable_energy',
  'irrigation', 'agricultural_productivity', 'commodity_prices', 'logistics', 'trading_partners',
] as const;

const cited = z.object({ statement: z.string(), citations: z.array(z.string()) });
const structuredSchema = z.object({
  recommendations: z.array(z.object({
    finding: z.string(),
    evidence: z.string(),
    action: z.string(),
    expected_benefit: z.string(),
    prerequisites: z.string(),
    uncertainty: z.string(),
    citations: z.array(z.string()),
  })).optional(),
  drivers: z.array(z.object({
    driver: z.enum(DRIVERS),
    basis: z.enum(['evidence', 'hypothesis', 'assumption']),
    relation: z.string(),
    citations: z.array(z.string()),
  })).optional(),
  evidence_points: z.array(cited).optional(),
  hypotheses: z.array(cited).optional(),
  assumptions: z.array(cited).optional(),
  conflicts: z.array(z.object({
    topic: z.string(),
    values: z.array(z.object({ evidence_id: z.string(), value_text: z.string() })),
    note: z.string().optional(),
  })).optional(),
  // Parts the server dropped because the cited evidence did not support them.
  withheld: z.record(z.string(), z.number()).optional(),
  // Deterministic studies cited by the reply; each is stored and opens at /studies/:id.
  studies: z.array(z.object({ id: z.string(), kind: z.string(), title: bilingual, status: z.string() })).optional(),
  // Google Search grounded results (via Gemini): shown verbatim with Google's search
  // suggestions, apart from the answer; never used as evidence for it.
  grounded_context: z.array(z.object({
    provider: z.string().nullable().optional(),
    attribution: z.string().nullable().optional(),
    model: z.string().nullable().optional(),
    text: z.string(),
    citations: z.array(z.object({
      url: z.string(), title: z.string().optional(), segment: z.string().optional(),
      source_class: z.string().optional(),
    }).passthrough()),
    search_suggestions: z.array(z.string()),
    queries: z.array(z.string()).optional(),
    retrieved_at: z.string().nullable().optional(),
  }).passthrough()).optional(),
  // The live study this reply was prepared as (its request id): the workspace can reopen it.
  study_id: z.string().optional(),
  // A data-based report given because the answer service failed (status 'data_report').
  data_report: z.object({
    label: bilingual,
    category: z.string(),
    reason: bilingual,
    incident: z.string(),
    sufficient: z.boolean(),
    data_last_updated: z.string().nullable(),
    web_search: z.string(),
    missing: z.array(bilingual),
    next_steps: z.array(bilingual),
    domains: z.array(z.string()),
  }).optional(),
  // Every web search of an AI answer failed: it rests on OSRIP's verified data only.
  web_notice: z.object({
    web_search: z.enum(['failed', 'not_configured']),
    data_last_updated: z.string().nullable(),
    research_cutoff: z.string().nullable(),
  }).optional(),
  // A failed request's reference for the administrator (no details of the failure).
  incident: z.string().optional(),
  failure: z.string().optional(),
  // How the answer was prepared, counted by the server from what was actually done.
  method: z.object({
    answer_provider: z.string().nullable().optional(),
    answer_model: z.string().nullable().optional(),
    answer_fallback: z.object({ from: z.string().nullable(), to: z.string(), reason: z.string() }).nullable().optional(),
    route: z.object({ numerical: z.boolean(), recent: z.boolean(), web_first: z.boolean() }).nullable().optional(),
    search_routes: z.array(z.object({
      provider: z.string(), role: z.string(), status: z.string().nullable().optional(), display_only: z.boolean(),
    })).optional(),
    provider_summaries: z.number().optional(),
    grounded_results: z.number().optional(),
    steps: z.array(z.string()),
    published_records: z.number(),
    calculations: z.number(),
    studies: z.number(),
    searches: z.number(),
    failed_searches: z.number(),
    search_languages: z.array(z.string()),
    web_results: z.number(),
    pages_read: z.number(),
    stale_sources: z.number(),
    undated_sources: z.number(),
  }).optional(),
});
export type StructuredReply = z.infer<typeof structuredSchema>;

const messageSchema = z.object({
  id: z.number(),
  role: z.enum(['user', 'assistant']),
  content: z.string(),
  // 'lookup': the labelled non-AI record list shown when no answer service is configured.
  status: z.enum(MESSAGE_STATUSES).nullable(),
  evidence: z.array(evidenceSchema),
  calculations: z.array(calculationSchema),
  citations: z.array(z.string()),
  suggestions: z.array(z.string()),
  model: z.string().nullable(),
  ai_generated: z.boolean(),
  created_at: z.string(),
  replayed: z.boolean().optional(),
  mode: z.enum(ASSISTANT_MODES).nullable().optional(),
  structured: structuredSchema.optional().default({}),
  // The persona that gave a reply (null: user messages, and replies from before personas).
  persona: z.string().nullable().optional(),
});
export type AssistantMessage = z.infer<typeof messageSchema>;

const conversationSchema = z.object({
  id: z.string(),
  title: z.string(),
  language: z.enum(['en', 'ar']),
  data_mode: z.enum(['verified_source', 'synthetic']),
  messages: z.array(messageSchema),
});
export type Conversation = z.infer<typeof conversationSchema>;

const summarySchema = z.object({
  id: z.string(), title: z.string(), language: z.string(), data_mode: z.string(), updated_at: z.string(),
});

const statusSchema = z.object({
  configured: z.boolean(),
  provider: z.string().nullable(),
  model: z.string().nullable(),
  fallback: z.string().nullable().optional(),
  limits: z.object({ per_minute: z.number(), per_hour: z.number(), per_day: z.number().optional() }),
  guest_answer_limit: z.number().optional(),
  web_research: z.boolean().optional(),
  web_research_provider: z.string().nullable().optional(),
  research_cutoff: z.string().nullable().optional(),
  // Research mode may cross-check with a second search route (two different routes configured).
  cross_check_available: z.boolean().optional(),
  max_message_chars: z.number(),
  suggestions: z.object({ en: z.array(z.string()), ar: z.array(z.string()) }),
  // The answer service's latest recorded outcome: ok, failing (replies are data-based
  // reports meanwhile), untested or not configured.
  health: z.object({
    state: z.enum(['ok', 'failing', 'untested', 'not_configured', 'unknown']),
    category: z.string().nullable(),
    at: z.string().nullable(),
  }).optional(),
  search_health: z.object({
    state: z.enum(['ok', 'failing', 'untested', 'not_configured', 'unknown']),
    category: z.string().nullable(),
    at: z.string().nullable(),
  }).optional(),
});
export type AssistantStatus = z.infer<typeof statusSchema>;

// ------------------------------------------------------------------ guest allowance

const allowanceSchema = z.object({
  limit: z.number(),
  used: z.number(),
  in_progress: z.number(),
  remaining: z.number(),
  authentication_required: z.boolean(),
  policy_version: z.number(),
});
export type Allowance = z.infer<typeof allowanceSchema>;

const guestStatusSchema = z.union([
  z.object({ authenticated: z.literal(true), linkable_history: z.boolean(), notice: bilingual }),
  z.object({
    authenticated: z.literal(false),
    allowance: allowanceSchema,
    notice: bilingual,
    linked: z.boolean(),
    expires_at: z.string(),
    conversations: z.array(summarySchema),
  }),
]);
export type GuestStatus = z.infer<typeof guestStatusSchema>;

const guestConversationSchema = conversationSchema.extend({ allowance: allowanceSchema });
const guestAskSchema = z.object({ message: messageSchema, conversation_id: z.string(), allowance: allowanceSchema });

/** The guest CSRF token (double submit); the anonymous identity itself is an HttpOnly cookie. */
function guestHeaders(extra: HeadersInit = {}): Headers {
  const headers = new Headers(extra);
  const match = document.cookie.split('; ').find((c) => c.startsWith('osrip_guest_csrf='));
  if (match) headers.set('X-Guest-CSRF', decodeURIComponent(match.slice('osrip_guest_csrf='.length)));
  return headers;
}

/** The visitor's allowance (issues the anonymous cookie on first use); signed-in users learn
 * whether guest history from this browser can be linked to their account. */
export function useGuestStatus(enabled: boolean) {
  return useQuery({
    queryKey: ['assistant', 'guest'],
    queryFn: () => apiJson('/assistant/guest', guestStatusSchema),
    enabled: adapterKind === 'http' && enabled,
    staleTime: 30_000,
  });
}

export function useGuestConversation(id: string | null) {
  return useQuery({
    queryKey: ['assistant', 'guest-conversation', id],
    queryFn: () => apiJson(`/assistant/guest/conversations/${id}`, guestConversationSchema, { headers: guestHeaders() }),
    enabled: adapterKind === 'http' && id !== null,
    retry: false,
  });
}

export interface GuestQuestion {
  content: string;
  language: 'en' | 'ar';
  request_id: string;
  conversation_id: string | null;
  data_mode: DataMode;
  web_research: boolean;
  mode: AssistantMode;
  persona?: string;
  cross_check?: boolean;
}

export function useGuestAsk() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: GuestQuestion) => {
      const init = jsonBody('POST', body);
      return apiJson('/assistant/guest/messages', guestAskSchema, { ...init, headers: guestHeaders(init.headers) });
    },
    onSuccess: (result) => {
      client.setQueryData<GuestStatus>(['assistant', 'guest'], (old) =>
        old && !old.authenticated ? { ...old, allowance: result.allowance } : old);
    },
    onSettled: (result) => {
      if (result) void client.invalidateQueries({ queryKey: ['assistant', 'guest-conversation', result.conversation_id] });
      void client.invalidateQueries({ queryKey: ['assistant', 'guest'] });
    },
  });
}

/** Explicit, authenticated move of this browser's guest conversations into the account. */
export function useLinkGuestHistory() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => apiJson('/assistant/guest/link', z.object({ linked_conversations: z.number() }), { method: 'POST' }),
    onSettled: () => {
      void client.invalidateQueries({ queryKey: ['assistant', 'guest'] });
      void client.invalidateQueries({ queryKey: ['assistant', 'conversations'] });
    },
  });
}

export function useAssistantStatus() {
  return useQuery({
    queryKey: ['assistant', 'status'],
    queryFn: () => apiJson('/assistant/status', statusSchema),
    enabled: adapterKind === 'http',
    staleTime: 60_000,
  });
}

export function useConversations(enabled: boolean) {
  return useQuery({
    queryKey: ['assistant', 'conversations'],
    queryFn: () => apiJson('/assistant/conversations', z.array(summarySchema)),
    enabled: adapterKind === 'http' && enabled,
  });
}

export function useConversation(id: string | null) {
  return useQuery({
    queryKey: ['assistant', 'conversation', id],
    queryFn: () => apiJson(`/assistant/conversations/${id}`, conversationSchema),
    enabled: adapterKind === 'http' && id !== null,
    retry: false,
  });
}

export function useCreateConversation() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: { language: 'en' | 'ar'; data_mode: DataMode }) =>
      apiJson('/assistant/conversations', conversationSchema, jsonBody('POST', body)),
    onSuccess: (conv) => {
      client.setQueryData(['assistant', 'conversation', conv.id], conv);
      void client.invalidateQueries({ queryKey: ['assistant', 'conversations'] });
    },
  });
}

export function useAsk(conversationId: string | null) {
  const client = useQueryClient();
  return useMutation({
    // request_id: a retry of the same question returns the stored reply instead of asking again.
    mutationFn: (body: {
      content: string; language: 'en' | 'ar'; request_id?: string; web_research: boolean; mode: AssistantMode;
      persona?: string; cross_check?: boolean;
    }) =>
      apiJson(`/assistant/conversations/${conversationId}/messages`, messageSchema, jsonBody('POST', body)),
    onSettled: () => {
      void client.invalidateQueries({ queryKey: ['assistant', 'conversation', conversationId] });
      void client.invalidateQueries({ queryKey: ['assistant', 'conversations'] });
    },
  });
}

// ------------------------------------------------------------------ progress and stopping

export const PROGRESS_STAGES = [
  'received', 'published_data', 'calculating', 'web_search', 'reading', 'checking', 'done', 'cancelled',
] as const;

const progressSchema = z.object({
  state: z.enum(['reserved', 'completed', 'released', 'cancelled']),
  cancel_requested: z.boolean(),
  stages: z.array(z.object({ stage: z.string(), at: z.string().optional(), label: bilingual })),
});
export type RequestProgress = z.infer<typeof progressSchema>;

function progressPath(requestId: string, guest: boolean, action: 'progress' | 'cancel'): string {
  return `/assistant/${guest ? 'guest/' : ''}requests/${requestId}/${action}`;
}

/** The real stages of a question while it is answered (polled once a second). The request
 * row appears a moment after sending, so a "not found" is simply tried again. */
export function useRequestProgress(requestId: string | null, guest: boolean) {
  return useQuery({
    queryKey: ['assistant', 'progress', requestId],
    queryFn: () => apiJson(progressPath(requestId ?? '', guest, 'progress'), progressSchema, { headers: guest ? guestHeaders() : undefined }),
    enabled: adapterKind === 'http' && requestId !== null,
    refetchInterval: 1000,
    retry: false,
    gcTime: 0,
  });
}

/** Stop a running question: it ends at its next step, unanswered and not counted. */
export function useCancelRequest() {
  return useMutation({
    mutationFn: ({ requestId, guest }: { requestId: string; guest: boolean }) =>
      apiJson(progressPath(requestId, guest, 'cancel'), progressSchema, { method: 'POST', headers: guest ? guestHeaders() : undefined }),
  });
}

// ------------------------------------------------------------------ server speech

const voiceStatusSchema = z.object({
  configured: z.boolean(),
  provider: z.string().nullable(),
  max_seconds: z.number(),
  languages: z.object({
    en: z.object({ locale: z.string(), voice: z.string() }),
    ar: z.object({ locale: z.string(), voice: z.string() }),
  }),
  // Each persona's configured server voice per language (from the assistant profile).
  personas: z.array(z.object({
    code: z.string(), default: z.boolean(), gender: z.enum(['male', 'female']),
    voices: z.object({ en: z.string(), ar: z.string() }),
  })).optional().default([]),
  stores_audio: z.boolean(),
});
export type VoiceStatus = z.infer<typeof voiceStatusSchema>;

export function useVoiceStatus() {
  return useQuery({
    queryKey: ['assistant', 'voice'],
    queryFn: () => apiJson('/assistant/voice', voiceStatusSchema),
    enabled: adapterKind === 'http',
    staleTime: 5 * 60_000,
  });
}

/** Speech to text of one recorded question (WAV). The text comes back for review; nothing is asked. */
export async function transcribe(audio: Blob, language: 'en' | 'ar', signal?: AbortSignal): Promise<string> {
  const result = await apiJson(`/assistant/voice/transcribe?language=${language}`, z.object({ text: z.string() }), {
    method: 'POST',
    body: audio,
    signal,
    headers: guestHeaders({ 'Content-Type': 'audio/wav' }),
  });
  return result.text;
}

/** Synthesised speech (MP3) of an assistant reply the visitor owns. */
export async function speakMessage(messageId: number, language: 'en' | 'ar', signal?: AbortSignal): Promise<Blob> {
  const init = jsonBody('POST', { message_id: messageId, language });
  const response = await apiFetch('/assistant/voice/speak', { ...init, signal, headers: guestHeaders(init.headers) });
  return response.blob();
}

const voiceCheck = z.object({
  name: z.string(),
  verified: z.boolean().nullable(),
  locale: z.string().nullable().optional(),
  gender: z.string().nullable().optional(),
});
const voicesSchema = z.object({
  configured: z.boolean(),
  personas: z.array(z.object({
    code: z.string(),
    gender: z.enum(['male', 'female']),
    configured: z.boolean(),
    voices: z.object({ ar: voiceCheck, en: voiceCheck }),
  })),
});
export type VoiceCheck = z.infer<typeof voiceCheck>;

/** Each persona's configured voice per language, and whether the speech service lists it. */
export function useVoiceVoices(enabled = true) {
  return useQuery({
    queryKey: ['assistant', 'voice', 'voices'],
    queryFn: () => apiJson('/assistant/voice/voices', voicesSchema),
    enabled: adapterKind === 'http' && enabled,
    staleTime: 10 * 60_000,
  });
}

/** A fixed sample sentence in the persona's configured voice (not arbitrary text). */
/** The voice test: the audio, and the exact words spoken (shown as its transcript). */
export async function testVoice(persona: string, language: 'en' | 'ar', signal?: AbortSignal): Promise<{ audio: Blob; transcript: string | null }> {
  const init = jsonBody('POST', { persona, language });
  const response = await apiFetch('/assistant/voice/test', { ...init, signal, headers: guestHeaders(init.headers) });
  const raw = response.headers.get('X-Transcript');
  let transcript: string | null = null;
  try {
    transcript = raw ? decodeURIComponent(raw) : null;
  } catch {
    transcript = null;
  }
  return { audio: await response.blob(), transcript };
}

/** The concise spoken summary of a stored shortage and surplus analysis. */
export async function speakAnalysis(analysisId: string, persona: string, language: 'en' | 'ar', signal?: AbortSignal): Promise<Blob> {
  const init = jsonBody('POST', { analysis_id: analysisId, persona, language });
  const response = await apiFetch('/assistant/voice/analysis', { ...init, signal, headers: guestHeaders(init.headers) });
  return response.blob();
}

/** One narration segment of a reply's study, spoken by the server (N1, N2, ...). */
export async function speakSegment(messageId: number, segmentId: string, language: 'en' | 'ar', signal?: AbortSignal): Promise<Blob> {
  const init = jsonBody('POST', { message_id: messageId, language, segment_id: segmentId });
  const response = await apiFetch('/assistant/voice/speak', { ...init, signal, headers: guestHeaders(init.headers) });
  return response.blob();
}

// ------------------------------------------------------------------ research review queue

const candidateSchema = z.object({
  id: z.string(),
  status: z.enum(['pending', 'accepted', 'rejected', 'duplicate']),
  domain: z.string(),
  indicator: z.string(),
  indicator_code: z.string().nullable(),
  value: z.string(),
  value_text: z.string(),
  unit: z.string(),
  geography: z.string(),
  period_label: z.string(),
  period_start: z.string().nullable(),
  period_end: z.string().nullable(),
  publication_date: z.string().nullable(),
  publisher: z.string(),
  source_title: z.string(),
  source_url: z.string(),
  source_class: z.enum(['official', 'international', 'research', 'secondary']),
  excerpt: z.string(),
  retrieved_at: z.string(),
  search_provider: z.string(),
  language: z.string(),
  checks: z.record(z.string(), z.unknown()),
  review_note: z.string().nullable(),
  reviewed_at: z.string().nullable(),
  created_at: z.string(),
});
export type ResearchCandidate = z.infer<typeof candidateSchema>;
export type CandidateStatus = ResearchCandidate['status'];

export function useResearchCandidates(status: CandidateStatus, enabled: boolean) {
  return useQuery({
    queryKey: ['research', 'candidates', status],
    queryFn: () => apiJson(`/research/candidates?status=${status}`, z.array(candidateSchema)),
    enabled: adapterKind === 'http' && enabled,
  });
}

export function useReviewCandidate() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ id, decision, note }: { id: string; decision: Exclude<CandidateStatus, 'pending'>; note: string }) =>
      apiJson(`/research/candidates/${id}/review`, candidateSchema, jsonBody('POST', { decision, note })),
    onSettled: () => void client.invalidateQueries({ queryKey: ['research'] }),
  });
}

// ------------------------------------------------------------------ Al Mulhim profile and memory

const codedSchema = z.object({ code: z.string(), en: z.string(), ar: z.string() });
const personaSchema = z.object({
  code: z.string(),
  default: z.boolean(),
  gender: z.enum(['male', 'female']),
  name: bilingual,
  meaning: bilingual,
  distinguished_from: bilingual.optional(),
  linguistic_note: bilingual.extend({ status: z.literal('interpretation') }).optional(),
  self_description: bilingual,
  introduction: bilingual,
  avatar: z.object({
    portrait: z.string(),
    figure: z.string().optional(),
    alt: bilingual,
    live_avatar_id: z.string().optional(),
  }),
  voices: z.object({
    azure: z.object({ en: z.string(), ar: z.string() }),
    realtime: z.object({ en: z.string().nullable().optional(), ar: z.string().nullable().optional() }),
  }),
});
export type Persona = z.infer<typeof personaSchema>;

const profileSchema = z.object({
  version: z.number(),
  sha256: z.string(),
  name: bilingual,
  meaning: bilingual,
  distinguished_from: bilingual,
  linguistic_note: bilingual.extend({ status: z.literal('interpretation') }),
  reference: z.object({ citation: z.string(), url: z.string(), cited_in: z.string(), verification: z.string() }),
  self_description: bilingual,
  introduction: bilingual,
  purpose: bilingual,
  capabilities: z.array(codedSchema),
  limitations: z.array(codedSchema),
  personas: z.array(personaSchema).min(1),
}).passthrough();
export type AssistantProfile = z.infer<typeof profileSchema>;

/** The assistant's approved, versioned profile with its personas (read-only on the server). */
export function useAssistantProfile(enabled = true) {
  return useQuery({
    queryKey: ['assistant', 'profile'],
    queryFn: () => apiJson('/assistant/profile', profileSchema),
    enabled: adapterKind === 'http' && enabled,
    staleTime: 10 * 60_000,
  });
}

const personaChoiceSchema = z.object({ persona: z.string().nullable(), stored: z.enum(['account', 'browser']) });

/** The signed-in person's saved persona (visitors keep theirs in this browser only). */
export function usePersonaChoice(enabled: boolean) {
  return useQuery({
    queryKey: ['assistant', 'persona'],
    queryFn: () => apiJson('/assistant/persona', personaChoiceSchema),
    enabled: adapterKind === 'http' && enabled,
    staleTime: 5 * 60_000,
  });
}

export function useSavePersonaChoice() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (persona: string) => apiJson('/assistant/persona', personaChoiceSchema, jsonBody('PUT', { persona })),
    onSuccess: (result) => client.setQueryData(['assistant', 'persona'], result),
  });
}

const memorySchema = z.object({
  profile_version: z.number().nullable(),
  retention: z.object({ policy: z.string(), en: z.string(), ar: z.string() }),
  conversations: z.number(),
  messages: z.number(),
  saved_research: z.number(),
  watchlist_items: z.number(),
  alert_rules: z.number(),
  never_retained: z.array(z.string()),
});
export type MemorySummary = z.infer<typeof memorySchema>;

export function useMemory(enabled: boolean) {
  return useQuery({
    queryKey: ['assistant', 'memory'],
    queryFn: () => apiJson('/assistant/memory', memorySchema),
    enabled: adapterKind === 'http' && enabled,
  });
}

export function useDeleteAllConversations() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => apiJson('/assistant/conversations', z.object({ deleted: z.number() }), { method: 'DELETE' }),
    onSettled: () => {
      void client.invalidateQueries({ queryKey: ['assistant'] });
    },
  });
}

export function useDeleteGuestConversation() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => apiFetch(`/assistant/guest/conversations/${id}`, { method: 'DELETE', headers: guestHeaders() }),
    onSettled: () => void client.invalidateQueries({ queryKey: ['assistant', 'guest'] }),
  });
}

const realtimeSchema = z.object({
  configured: z.boolean(),
  agent_sdk_installed: z.boolean(),
  missing: z.array(z.string()),
  avatar: z.object({ configured: z.boolean(), provider: z.string().nullable(), reason: z.string().nullable() }),
  fallback: z.string(),
  note: bilingual,
});
export type RealtimeStatus = z.infer<typeof realtimeSchema>;

export function useRealtimeVoiceStatus(enabled = true) {
  return useQuery({
    queryKey: ['assistant', 'voice-realtime'],
    queryFn: () => apiJson('/assistant/voice/realtime', realtimeSchema),
    enabled: adapterKind === 'http' && enabled,
    staleTime: 5 * 60_000,
  });
}

export function useDeleteConversation() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => apiFetch(`/assistant/conversations/${id}`, { method: 'DELETE' }),
    onSuccess: (_r, id) => client.removeQueries({ queryKey: ['assistant', 'conversation', id] }),
    onSettled: () => void client.invalidateQueries({ queryKey: ['assistant', 'conversations'] }),
  });
}
