import { Loader2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { Markdown } from './Markdown';
import { usePersona } from './persona';
import { PersonaImage } from './PersonaImage';
import { withoutMarkers } from './StructuredReply';
import { PROGRESS_STAGES, useRequestProgress } from '@/api/assistant';
import { useAppLanguage } from '@/lib/useAppLanguage';
import { useAnswerStream } from '@/state/answerStream';

/**
 * The answer while it is written: the stage reached (searching, reading, analysing, writing,
 * checking) and the text so far, as the server streams it (sentences that have passed the
 * evidence check, in order; no simulated typing). Where the event stream is not available, the
 * stage is polled instead and the text appears when the answer is complete. The stored reply
 * replaces this when it arrives. Sources and evidence markers stay hidden, as in the reply.
 */
export function StreamingAnswer({ requestId, guest }: { requestId: string | null; guest: boolean }) {
  const { t } = useTranslation();
  const language = useAppLanguage();
  const { persona } = usePersona();
  const stream = useAnswerStream(requestId, guest);
  const progress = useRequestProgress(stream.live ? null : requestId, guest);
  const polled = (progress.data?.stages ?? []).map((s) => s.stage)
    .filter((s): s is (typeof PROGRESS_STAGES)[number] => (PROGRESS_STAGES as readonly string[]).includes(s)).at(-1);
  const stage = stream.live ? stream.stage : polled ?? null;
  const writing = stream.text.length > 0;
  const label = stream.live
    ? t(`answerStream.phase.${stream.phase}`)
    : stage && stage !== 'received' && (PROGRESS_STAGES as readonly string[]).includes(stage)
      ? t(`workflow.stage.${stage as (typeof PROGRESS_STAGES)[number]}`)
      : t('workflow.working');
  return (
    <li className="glass-card flex flex-col gap-2 rounded-2xl rounded-es-md border p-4 text-base leading-relaxed shadow-card sm:p-5"
      data-testid="assistant-loading" data-stage={stage ?? ''} data-phase={stream.live ? stream.phase : ''}
      data-segments={stream.segments} aria-busy="true">
      <p className="flex flex-wrap items-center gap-1.5 text-sm text-muted-foreground" role="status">
        <span className="inline-flex items-center gap-1.5 font-semibold text-foreground">
          <PersonaImage src={persona.avatar.portrait} alt="" width={20} height={20} className="size-5 rounded-full object-cover object-top" draggable={false} />
          {persona.name[language]}
        </span>
        <Loader2 aria-hidden="true" className="size-3.5 animate-spin motion-reduce:animate-none" />
        <span data-testid="answer-stream-phase">{label}</span>
      </p>
      {writing ? (
        <div className="flex flex-col gap-3" data-testid="answer-stream-text">
          <Markdown text={withoutMarkers(stream.text)} cite={() => null} />
          <span aria-hidden="true" className="inline-block h-4 w-1.5 animate-pulse rounded-sm bg-primary motion-reduce:animate-none" />
        </div>
      ) : null}
      {writing ? <p className="text-xs text-muted-foreground" data-testid="answer-stream-note">{t('answerStream.note')}</p> : null}
    </li>
  );
}
