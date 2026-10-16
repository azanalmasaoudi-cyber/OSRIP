import { createContext, useCallback, useContext, useId, useMemo, useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

import { PersonaImage } from './PersonaImage';
import { useAssistantProfile, usePersonaChoice, useSavePersonaChoice, type Persona } from '@/api/assistant';
import { useMe } from '@/api/auth';
import { adapterKind } from '@/api/config';
import { useAppLanguage } from '@/lib/useAppLanguage';
import { cn } from '@/lib/utils';

/**
 * The selectable assistant personas (assistant profile version 3): Al Mulhim and Ilham.
 * A persona changes who speaks: name, introduction, portrait and voice. Knowledge, tools,
 * permissions, sources, conversation history and the guest allowance are the same for both.
 *
 * The choice is kept on the account for signed-in people (so it follows them to another
 * device) and in this browser for visitors without an account.
 */

export type PersonaView = Pick<Persona, 'code' | 'default' | 'gender' | 'name' | 'avatar'>;

const STORAGE_KEY = 'osrip.assistant.persona';

// The same names and portraits as profile version 3, shown until the profile has loaded.
const BUILT_IN: PersonaView[] = [
  {
    code: 'mulhim', default: true, gender: 'male', name: { en: 'Al Mulhim', ar: 'المُلْهِم' },
    avatar: {
      portrait: '/images/assistant/mulhim-portrait-432.jpg', figure: '/images/assistant/mulhim-figure-600.jpg',
      alt: {
        en: 'Al Mulhim: generated image of a fictional Omani man in a white dishdasha and an embroidered kumma. Not a real person.',
        ar: 'المُلْهِم: صورة مولّدة لرجل عُماني خيالي يرتدي الدشداشة البيضاء والكمّة المطرّزة. ليس شخصاً حقيقياً.',
      },
    },
  },
  {
    code: 'ilham', default: false, gender: 'female', name: { en: 'Ilham', ar: 'إلهام' },
    avatar: {
      portrait: '/images/assistant/ilham-portrait-432.jpg', figure: '/images/assistant/ilham-figure-600.jpg',
      alt: {
        en: 'Ilham: generated image of a fictional Omani woman in a headscarf and an abaya with embroidered sleeves. Not a real person.',
        ar: 'إلهام: صورة مولّدة لامرأة عُمانية خيالية ترتدي غطاء الرأس وعباءة بأكمام مطرّزة. ليست شخصاً حقيقياً.',
      },
    },
  },
];

function readStored(): string | null {
  try {
    return window.localStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
}

function writeStored(code: string): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, code);
  } catch {
    // Storage blocked: the choice lasts for this visit.
  }
}

interface PersonaState {
  personas: PersonaView[];
  persona: PersonaView;
  /** Look up a persona by code (a message's persona); the default when unknown. */
  byCode: (code: string | null | undefined) => PersonaView;
  choose: (code: string) => void;
  storedOn: 'account' | 'browser';
}

function resolve(list: PersonaView[], code: string | null | undefined): PersonaView {
  return list.find((p) => p.code === code) ?? list.find((p) => p.default) ?? (list[0] as PersonaView);
}

const Ctx = createContext<PersonaState | null>(null);

export function PersonaProvider({ children }: { children: ReactNode }) {
  const profile = useAssistantProfile(adapterKind === 'http');
  const me = useMe();
  const signedIn = Boolean(me.data?.authenticated);
  const saved = usePersonaChoice(signedIn);
  const save = useSavePersonaChoice();
  // A choice made in this visit wins; then the account's saved choice; then this browser's.
  const [picked, setPicked] = useState<string | null>(null);
  const [stored] = useState<string | null>(readStored);
  const personas = useMemo<PersonaView[]>(() => profile.data?.personas ?? BUILT_IN, [profile.data]);
  const code = picked ?? (signedIn ? saved.data?.persona : null) ?? stored;
  const persona = resolve(personas, code);
  const { mutate } = save;
  const choose = useCallback((next: string) => {
    setPicked(next);
    writeStored(next);
    if (signedIn) mutate(next);
  }, [signedIn, mutate]);
  const byCode = useCallback((c: string | null | undefined) => resolve(personas, c), [personas]);
  const value = useMemo<PersonaState>(
    () => ({ personas, persona, byCode, choose, storedOn: signedIn ? 'account' : 'browser' }),
    [personas, persona, byCode, choose, signedIn],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

const FALLBACK: PersonaState = {
  personas: BUILT_IN,
  persona: resolve(BUILT_IN, null),
  byCode: (c) => resolve(BUILT_IN, c),
  choose: () => undefined,
  storedOn: 'browser',
};

export function usePersona(): PersonaState {
  return useContext(Ctx) ?? FALLBACK;
}

/** Choose who answers: Al Mulhim or Ilham, with their portraits and names in both languages. */
export function PersonaPicker({ className, compact = false }: { className?: string; compact?: boolean }) {
  const { t } = useTranslation();
  const language = useAppLanguage();
  const other = language === 'ar' ? 'en' : 'ar';
  const { personas, persona, choose, storedOn } = usePersona();
  const name = useId();
  return (
    <fieldset className={cn('flex flex-col gap-1.5', className)} data-testid="persona-picker" data-selected={persona.code}>
      <legend className={cn('mb-1 text-xs font-semibold', compact && 'sr-only')}>{t('persona.choose')}</legend>
      <div className="flex flex-wrap gap-2">
        {personas.map((p) => {
          const checked = p.code === persona.code;
          return (
            <label key={p.code} data-testid={`persona-option-${p.code}`} data-checked={checked ? 'true' : 'false'}
              className={cn(
                'flex min-h-11 cursor-pointer items-center gap-2 rounded-full border py-1 ps-1 pe-3 text-start transition-colors has-[:focus-visible]:outline-3 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-ring',
                checked ? 'border-primary bg-primary/10 font-semibold' : 'border-border-strong/50 hover:bg-muted',
              )}>
              <input type="radio" name={name} value={p.code} checked={checked} onChange={() => choose(p.code)} className="sr-only" />
              <PersonaImage src={p.avatar.portrait} alt="" width={36} height={36} className="size-9 rounded-full object-cover object-top" draggable={false} />
              <span className="flex flex-col text-sm leading-tight" lang={language}>
                {p.name[language]}
                <span className="text-xs font-normal text-muted-foreground" lang={other}>{p.name[other]}</span>
              </span>
            </label>
          );
        })}
      </div>
      {compact ? null : (
        <p className="text-xs text-muted-foreground" data-testid="persona-note">
          {t('persona.shared')} {storedOn === 'account' ? t('persona.storedAccount') : t('persona.storedBrowser')}
        </p>
      )}
    </fieldset>
  );
}
