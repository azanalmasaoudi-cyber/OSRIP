import { ListChecks, Target } from 'lucide-react';
import { useId, useState } from 'react';
import { useTranslation } from 'react-i18next';

import type { StructuredReply } from '@/api/assistant';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { useAppLanguage } from '@/lib/useAppLanguage';

/**
 * Objectives before recommendations. When Al Mulhim was asked for recommendations without an
 * objective, it gives the results and the analysis and asks which objectives to serve: the person
 * ticks them here and sends them as the next message (written out, so it can be read before it
 * is sent). When the objectives were known, they are shown with the answer.
 */
export function ReplyObjectives({ objectives, onAsk }: {
  objectives: NonNullable<StructuredReply['objectives']>;
  onAsk: (text: string) => void;
}) {
  const { t } = useTranslation();
  const language = useAppLanguage();
  const id = useId();
  const [chosen, setChosen] = useState<string[]>([]);
  if (objectives.status === 'known') {
    return (
      <p className="flex flex-wrap items-center gap-2 text-sm" data-testid="reply-objectives" data-status="known">
        <span className="font-medium">{t('assistant.objectives.known')}</span>
        {objectives.known.map((o) => <Badge key={o.code} variant="outline"><Target aria-hidden="true" />{o.name[language]}</Badge>)}
      </p>
    );
  }
  const names = objectives.options.filter((o) => chosen.includes(o.code)).map((o) => o.name[language]);
  return (
    <fieldset className="flex flex-col gap-3 rounded-lg border border-border border-s-4 border-s-copper bg-card p-4" data-testid="reply-objectives" data-status="ask">
      <legend className="sr-only">{t('assistant.objectives.question')}</legend>
      <p className="text-sm font-medium" aria-hidden="true">{t('assistant.objectives.question')}</p>
      <div className="flex flex-wrap gap-2">
        {objectives.options.map((o) => (
          <label key={o.code} htmlFor={`${id}-${o.code}`}
            className="inline-flex min-h-10 cursor-pointer items-center gap-2 rounded-full border border-border px-3 text-sm has-[:checked]:border-primary has-[:checked]:bg-primary-soft">
            <input id={`${id}-${o.code}`} type="checkbox" className="size-4 accent-primary" checked={chosen.includes(o.code)}
              data-testid={`reply-objective-${o.code}`}
              onChange={(e) => setChosen((c) => (e.target.checked ? [...c, o.code] : c.filter((x) => x !== o.code)))} />
            {o.name[language]}
          </label>
        ))}
      </div>
      <Button size="sm" className="w-fit" disabled={!chosen.length} data-testid="reply-objectives-send"
        onClick={() => onAsk(t('assistant.objectives.followUp', { objectives: names.join(language === 'ar' ? '، ' : ', ') }))}>
        <ListChecks aria-hidden="true" />{t('assistant.objectives.send')}
      </Button>
    </fieldset>
  );
}
