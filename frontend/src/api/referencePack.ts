import { useQuery } from '@tanstack/react-query';
import { z } from 'zod';

import { apiJson } from './client';
import { adapterKind } from './index';

/**
 * The curated reference pack (GET /reference-pack): an extract of official
 * publications and statements checked up to its research cutoff. It is not a live
 * or official feed; the page says so wherever the pack is summarised.
 */
const bilingual = z.object({ en: z.string(), ar: z.string() });

const referencePackSchema = z.object({
  pack: z
    .object({
      code: z.string(),
      title: z.string(),
      research_cutoff: z.string(),
      document: z.string(),
      record_count: z.number(),
      published_records: z.number(),
      loaded_at: z.string(),
      status_note: bilingual,
    })
    .nullable(),
  sources: z.array(
    z.object({
      code: z.string(),
      publisher: z.string(),
      title: z.string(),
      publication: z.string(),
      accessed_on: z.string(),
      role: z.string(),
      url: z.string().nullable(),
      locations: z.string().nullable(),
      published_records: z.number(),
    }),
  ),
  notes: z.array(
    z.object({
      code: z.string(),
      title: bilingual,
      body: bilingual,
      source_codes: z.array(z.string()),
      sections: z.array(z.string()),
    }),
  ),
});
export type ReferencePack = z.infer<typeof referencePackSchema>;
export type DataQualityNote = ReferencePack['notes'][number];

export function useReferencePack() {
  return useQuery({
    queryKey: ['reference-pack'],
    queryFn: () => apiJson('/reference-pack', referencePackSchema),
    enabled: adapterKind === 'http',
    staleTime: 10 * 60 * 1000,
  });
}
