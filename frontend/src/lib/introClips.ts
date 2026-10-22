import { useQuery } from '@tanstack/react-query';
import { z } from 'zod';

/**
 * Pre-recorded introductions (made in Canva) for each persona, listed in
 * public/audio/intro/manifest.json. A slot without a file is not offered: nothing refers to a
 * file that does not exist. A clip is always presented as a recording, never as live speech,
 * and plays only after the person presses Play (through the shared player, so it stops any
 * other audio and "Stop audio" stops it).
 */

const FILE = /^[a-z0-9][a-z0-9._-]{0,80}\.(mp3|m4a|ogg|wav)$/;
const slot = z.object({ src: z.string().regex(FILE).nullable(), transcript: z.string().max(2000).nullable() });
const manifestSchema = z.object({
  clips: z.record(z.string(), z.object({ ar: slot.optional(), en: slot.optional() })),
});

export interface IntroClip {
  url: string;
  transcript: string | null;
}

const BASE = `${import.meta.env.BASE_URL}audio/intro/`;

async function loadManifest(): Promise<z.infer<typeof manifestSchema> | null> {
  try {
    const response = await fetch(`${BASE}manifest.json`, { cache: 'no-cache' });
    if (!response.ok) return null;
    const parsed = manifestSchema.safeParse(await response.json());
    return parsed.success ? parsed.data : null;
  } catch {
    return null;
  }
}

export function clipFrom(manifest: z.infer<typeof manifestSchema> | null, persona: string, language: 'ar' | 'en'): IntroClip | null {
  const entry = manifest?.clips[persona]?.[language];
  if (!entry?.src) return null;
  return { url: `${BASE}${entry.src}`, transcript: entry.transcript };
}

/** The persona's recorded introduction in this language, or null when none is supplied. */
export function useIntroClip(persona: string, language: 'ar' | 'en'): IntroClip | null {
  const manifest = useQuery({ queryKey: ['intro-clips'], queryFn: loadManifest, staleTime: Infinity, retry: false });
  return clipFrom(manifest.data ?? null, persona, language);
}

/** The clip's audio, for the shared player (fetched only when the person presses Play). */
export async function clipBlob(clip: IntroClip): Promise<Blob> {
  const response = await fetch(clip.url);
  if (!response.ok) throw new Error(`clip ${response.status}`);
  return response.blob();
}
