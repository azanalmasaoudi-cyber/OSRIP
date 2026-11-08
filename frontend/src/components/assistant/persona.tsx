import { createContext, useCallback, useContext, useId, useMemo, useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

import { PersonaImage } from './PersonaImage';
import { useAssistantProfile, usePersonaChoice, useSavePersonaChoice, type Persona } from '@/api/assistant';
import { useMe } from '@/api/auth';
import { adapterKind } from '@/api/config';
import { useAppLanguage } from '@/lib/useAppLanguage';
import { cn } from '@/lib/utils';

/**
 * The assistant's persona (assistant profile version 4): Al Mulhim, the only one offered. The
 * profile could list several (version 3 had Al Mulhim and Ilham); a choice is shown only when it
 * does. A persona changes who speaks: name, introduction, portrait and voice. Knowledge, tools,
 * permissions, sources, conversation history and the guest allowance are shared.
 *
 * Replies given by a persona that is no longer offered keep their text, under a neutral name and
 * badge (never relabelled as the current persona). A choice, where there is one, is kept on the
 * account for signed-in people and in this browser for visitors without an account.
 */

export type PersonaView = Pick<Persona, 'code' | 'default' | 'gender' | 'name' | 'avatar'>;

const STORAGE_KEY = 'osrip.assistant.persona';

// The same name and portrait as profile version 4, shown until the profile has loaded.
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
  /** The author of a stored reply by its persona code (see ``author``). */
  byCode: (code: string | null | undefined) => PersonaView;
  choose: (code: string) => void;
  storedOn: 'account' | 'browser';
}

function resolve(list: PersonaView[], code: string | null | undefined): PersonaView {
  return list.find((p) => p.code === code) ?? list.find((p) => p.default) ?? (list[0] as PersonaView);
}

/** The author of a stored reply: its persona, or, for a persona no longer offered, a neutral
 * name and the "AI" badge (an empty portrait), with the current persona's voice. */
function author(list: PersonaView[], code: string | null | undefined): PersonaView {
  const found = list.find((p) => p.code === code);
  if (found || !code) return found ?? resolve(list, null);
  const current = resolve(list, null);
  return {
    code, default: false, gender: current.gender,
    name: { en: 'Earlier assistant persona', ar: 'شخصية سابقة للمساعد' },
    avatar: { portrait: '', alt: { en: '', ar: '' } },
  };
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
  const byCode = useCallback((c: string | null | undefined) => author(personas, c), [personas]);
  const value = useMemo<PersonaState>(
    () => ({ personas, persona, byCode, choose, storedOn: signedIn ? 'account' : 'browser' }),
    [personas, persona, byCode, choose, signedIn],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

const FALLBACK: PersonaState = {
  personas: BUILT_IN,
  persona: resolve(BUILT_IN, null),
  byCode: (c) => author(BUILT_IN, c),
  choose: () => undefined,
  storedOn: 'browser',
};

export function usePersona(): PersonaState {
  return useContext(Ctx) ?? FALLBACK;
}

/** The conversation header's compact choice, as one segmented control: only when the profile
 * offers more than one persona (version 4 offers one, Al Mulhim). */
export function PersonaSwitch({ className }: { className?: string }) {
  const { t } = useTranslation();
  const language = useAppLanguage();
  const { personas, persona, choose } = usePersona();
  const name = useId();
  if (personas.length < 2) return null;
  return (
    <fieldset className={cn('flex rounded-full border border-border-strong/50 p-0.5', className)} data-testid="persona-picker" data-selected={persona.code}>
      <legend className="sr-only">{t('persona.choose')}</legend>
      {personas.map((p) => {
        const checked = p.code === persona.code;
        return (
          <label key={p.code} data-testid={`persona-option-${p.code}`} data-checked={checked ? 'true' : 'false'}
            className={cn('cursor-pointer rounded-full px-2.5 py-1 text-xs font-medium whitespace-nowrap transition-colors has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-ring motion-reduce:transition-none',
              checked ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:bg-muted hover:text-foreground')}>
            <input type="radio" name={name} value={p.code} checked={checked} onChange={() => choose(p.code)} className="sr-only" />
            {p.name[language]}
          </label>
        );
      })}
    </fieldset>
  );
}

/** Choose who answers, with portraits and names in both languages: only when the profile offers
 * more than one persona. */
export function PersonaPicker({ className, compact = false }: { className?: string; compact?: boolean }) {
  const { t } = useTranslation();
  const language = useAppLanguage();
  const other = language === 'ar' ? 'en' : 'ar';
  const { personas, persona, choose, storedOn } = usePersona();
  const name = useId();
  if (personas.length < 2) return null;
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
