import { ClipboardList } from 'lucide-react';
import { useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';

import type { AssistantMode } from '@/api/assistant';
import { Button } from '@/components/ui/button';
import { SelectField } from '@/components/ui/select';
import {
  BRIEF_DOMAINS,
  BRIEF_GOALS,
  BRIEF_MODE,
  briefDomains,
  briefGoals,
  buildResearchBrief,
  type BriefDomain,
  type BriefGoal,
  type BriefLanguage,
} from '@/lib/researchBrief';
import { useAppLanguage } from '@/lib/useAppLanguage';

/**
 * A study request built from a domain and a goal, written in the answer language. "Use this
 * draft" puts it in the message box and selects the matching answer mode; nothing is sent. The
 * person reviews or edits it and presses Send, and only then do the usual permissions, provider
 * and guest allowance apply. It asks for evidence; it cannot make the answer supply all of it.
 */
export function ResearchBriefBuilder({ language, disabled, maxLength, onDraft }: {
  /** The answer language: the draft is written in it. */
  language: BriefLanguage;
  disabled: boolean;
  maxLength: number;
  onDraft: (draft: string, mode: AssistantMode) => void;
}) {
  const { t } = useTranslation();
  const appLanguage = useAppLanguage();
  const [domain, setDomain] = useState<BriefDomain>('electricity');
  const [goal, setGoal] = useState<BriefGoal>('trend');
  const details = useRef<HTMLDetailsElement>(null);
  const draft = buildResearchBrief(language, domain, goal);
  const tooLong = draft.length > maxLength;
  const use = () => {
    // Closed again, so the message box with the draft is in view (on phones too).
    if (details.current) details.current.open = false;
    onDraft(draft, BRIEF_MODE[goal]);
  };
  return (
    <details ref={details} className="rounded-md border border-primary/25 bg-primary/5 text-sm" data-testid="research-brief">
      <summary className="flex min-h-9 cursor-pointer items-center gap-1.5 px-3 py-2 font-semibold">
        <ClipboardList aria-hidden="true" className="size-4 text-primary" />{t('assistant.brief.open')}
      </summary>
      <div className="flex flex-col gap-3 px-3 pt-1 pb-3">
        <div className="grid gap-3 sm:grid-cols-2">
          <SelectField label={t('assistant.brief.domain')} value={domain} disabled={disabled}
            onValueChange={(v) => setDomain(BRIEF_DOMAINS.find((d) => d === v) ?? 'electricity')}
            options={BRIEF_DOMAINS.map((d) => ({ value: d, label: briefDomains[appLanguage][d] }))}
            data-testid="research-brief-domain" />
          <SelectField label={t('assistant.brief.goal')} value={goal} disabled={disabled}
            onValueChange={(v) => setGoal(BRIEF_GOALS.find((g) => g === v) ?? 'trend')}
            options={BRIEF_GOALS.map((g) => ({ value: g, label: briefGoals[appLanguage][g] }))}
            data-testid="research-brief-goal" />
        </div>
        <p className="text-xs text-muted-foreground">{t('assistant.brief.note')}</p>
        {tooLong ? <p role="status" className="text-xs text-destructive" data-testid="research-brief-too-long">{t('assistant.brief.tooLong')}</p> : null}
        <Button type="button" size="sm" variant="outline" className="w-fit" disabled={disabled || tooLong}
          onClick={use} data-testid="research-brief-use">
          {t('assistant.brief.use')}
        </Button>
      </div>
    </details>
  );
}
