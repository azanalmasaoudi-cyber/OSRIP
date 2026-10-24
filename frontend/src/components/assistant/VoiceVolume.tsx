import { Volume2 } from 'lucide-react';
import { useId } from 'react';
import { useTranslation } from 'react-i18next';

import { useVoiceVolume } from '@/lib/useVoiceVolume';

/** The shared voice volume (spoken answers, voice tests and spoken summaries). */
export function VoiceVolume({ testId = 'voice-volume', compact = false }: { testId?: string; compact?: boolean }) {
  const { t } = useTranslation();
  const id = useId();
  const [volume, setVolume] = useVoiceVolume();
  return (
    <span className="inline-flex items-center gap-1.5 text-xs">
      <Volume2 aria-hidden="true" className="size-3.5 text-muted-foreground" />
      <label htmlFor={id} className="sr-only">{t('voicePanel.volume')}</label>
      <input id={id} type="range" min={0} max={100} step={5} value={volume} onChange={(e) => setVolume(Number(e.target.value))}
        className={compact ? 'h-1 w-16 accent-primary' : 'h-1 w-24 accent-primary'} data-testid={testId} aria-valuetext={`${volume}%`} />
      <span className="w-8 tabular-nums text-muted-foreground" dir="ltr">{volume}%</span>
    </span>
  );
}
