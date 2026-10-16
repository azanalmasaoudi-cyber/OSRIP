import type { CSSProperties } from 'react';

import type { OrbState } from './AssistantContext';
import { usePersona, type PersonaView } from './persona';
import { PersonaImage } from './PersonaImage';
import { useAppLanguage } from '@/lib/useAppLanguage';
import { cn } from '@/lib/utils';

export const ORB_STATE_KEY = {
  idle: 'orb.idle',
  listening: 'orb.listening',
  processing: 'orb.processing',
  speaking: 'orb.speaking',
  error: 'orb.error',
} as const satisfies Record<OrbState, string>;

/**
 * The chosen persona's still portrait (styles: .assistant-avatar in index.css): Al Mulhim or
 * Ilham, generated images of fictional people recorded in frontend/assets/editorial/
 * sources.json. ``shape="figure"`` shows the larger half-length image (the Talk workspace).
 * Its data-state comes from real events only (microphone open, request in flight, audio
 * playing, failure). While speech plays, the ring and level bars follow the measured loudness
 * of the audio through the --assistant-voice CSS variable (set by lib/voicePlayer): a simple
 * speaking animation, not lip synchronisation. Under reduced motion the image stays still and
 * the state is shown by colour and the written status only.
 */
export function AssistantAvatar({
  state,
  size = '3.5rem',
  className,
  decorative = true,
  shape = 'portrait',
  persona: given,
}: {
  state: OrbState;
  size?: string;
  className?: string;
  decorative?: boolean;
  shape?: 'portrait' | 'figure';
  persona?: PersonaView;
}) {
  const language = useAppLanguage();
  const { persona: chosen } = usePersona();
  const persona = given ?? chosen;
  const figure = shape === 'figure';
  const src = figure ? persona.avatar.figure ?? persona.avatar.portrait : persona.avatar.portrait;
  return (
    <span
      className={cn('assistant-avatar shrink-0', className)}
      data-state={state}
      data-shape={figure ? 'figure' : undefined}
      data-persona={persona.code}
      data-testid="assistant-avatar"
      style={{ '--avatar-size': size } as CSSProperties}
      aria-hidden={decorative ? 'true' : undefined}
    >
      <PersonaImage src={src} alt={decorative ? '' : persona.avatar.alt[language]} width={figure ? 600 : 432} height={figure ? 800 : 432}
        draggable={false} />
      <span className="assistant-avatar-bars" aria-hidden="true">
        <span /><span /><span />
      </span>
    </span>
  );
}
