import { createContext, useCallback, useContext, useMemo, type ReactNode } from 'react';

import { useAssistantProfile, type Persona } from '@/api/assistant';
import { adapterKind } from '@/api/config';

/**
 * The assistant: Al Mulhim, the only active persona (assistant profile version 4). There is no
 * persona to choose, store or show a picker for: every question is answered by the profile's
 * default persona, with its name, introduction, portrait and voice.
 *
 * Replies given by a persona that is no longer active (Ilham, profile version 3) keep their text
 * in the conversation history, under a neutral name and badge: they stay readable and are never
 * relabelled as Al Mulhim.
 */

export type PersonaView = Pick<Persona, 'code' | 'default' | 'gender' | 'name' | 'avatar'>;

// The same name and portrait as profile version 4, shown until the profile has loaded.
const BUILT_IN: PersonaView = {
  code: 'mulhim', default: true, gender: 'male', name: { en: 'Al Mulhim', ar: 'المُلْهِم' },
  avatar: {
    portrait: '/images/assistant/mulhim-portrait-432.jpg', figure: '/images/assistant/mulhim-figure-600.jpg',
    alt: {
      en: 'Al Mulhim: generated image of a fictional Omani man in a white dishdasha and an embroidered kumma. Not a real person.',
      ar: 'المُلْهِم: صورة مولّدة لرجل عُماني خيالي يرتدي الدشداشة البيضاء والكمّة المطرّزة. ليس شخصاً حقيقياً.',
    },
  },
};

interface PersonaState {
  /** Al Mulhim (the profile's default persona). */
  persona: PersonaView;
  /** The author of a stored reply by its persona code (see ``author``). */
  byCode: (code: string | null | undefined) => PersonaView;
}

/** The active persona: the profile's default (Al Mulhim), whatever else it lists. */
function active(list: PersonaView[]): PersonaView {
  return list.find((p) => p.default) ?? list.find((p) => p.code === BUILT_IN.code) ?? BUILT_IN;
}

/** The author of a stored reply: Al Mulhim, or, for a persona no longer active, a neutral name
 * and the "AI" badge (an empty portrait), read with Al Mulhim's voice. */
function author(current: PersonaView, code: string | null | undefined): PersonaView {
  if (!code || code === current.code) return current;
  return {
    code, default: false, gender: current.gender,
    name: { en: 'Earlier assistant persona', ar: 'شخصية سابقة للمساعد' },
    avatar: { portrait: '', alt: { en: '', ar: '' } },
  };
}

const Ctx = createContext<PersonaState | null>(null);

export function PersonaProvider({ children }: { children: ReactNode }) {
  const profile = useAssistantProfile(adapterKind === 'http');
  const persona = useMemo(() => active(profile.data?.personas ?? [BUILT_IN]), [profile.data]);
  const byCode = useCallback((c: string | null | undefined) => author(persona, c), [persona]);
  const value = useMemo<PersonaState>(() => ({ persona, byCode }), [persona, byCode]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

const FALLBACK: PersonaState = { persona: BUILT_IN, byCode: (c) => author(BUILT_IN, c) };

export function usePersona(): PersonaState {
  return useContext(Ctx) ?? FALLBACK;
}
