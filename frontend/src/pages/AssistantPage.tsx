import { FlaskConical, Mic, Play, Sigma } from 'lucide-react';
import { useId, useMemo, useRef, useState } from 'react';
import { Link, useSearchParams } from 'react-router';
import { useTranslation } from 'react-i18next';

import { speakAnalysis, useAssistantStatus, useVoiceStatus } from '@/api/assistant';
import { OPTION_KINDS, SECTORS, spokenText, useBalance, useRunBalance, type Sector } from '@/api/balance';
import { adapterKind } from '@/api/config';
import { useAssistantUi } from '@/components/assistant/AssistantContext';
import { AssistantChat, type AskFromOutside } from '@/components/assistant/AssistantPanel';
import { AssistantIdentityCard } from '@/components/assistant/AssistantIdentityCard';
import { usePersona } from '@/components/assistant/persona';
import { PageHeader } from '@/components/common/PageHeader';
import { fromBalance, fromStudy, type Labels } from '@/components/results/model';
import { ResultsPanel } from '@/components/results/ResultsPanel';
import { Button } from '@/components/ui/button';
import { Segmented } from '@/components/ui/segmented';
import { SelectField } from '@/components/ui/select';
import { useNarration } from '@/components/workspace/useNarration';
import { speak, voiceFor } from '@/lib/speech';
import { useAppLanguage } from '@/lib/useAppLanguage';
import { playAudio } from '@/lib/voicePlayer';
import { useLiveStudy } from '@/state/liveStudy';
import { useDataMode } from '@/state/useDataMode';
import { usePreservedSearch } from '@/state/usePreservedSearch';

const SECTOR_KEY = 'osrip.assistant.sector';

function readSector(): Sector {
  try {
    const v = window.localStorage.getItem(SECTOR_KEY);
    return (SECTORS as readonly string[]).includes(v ?? '') ? (v as Sector) : 'electricity';
  } catch {
    return 'electricity';
  }
}

function useResultLabels(): Labels {
  const { t } = useTranslation();
  return useMemo(() => ({
    balanceStatus: { surplus: t('balance.balanceStatus.surplus'), shortfall: t('balance.balanceStatus.shortfall'),
      balanced: t('balance.balanceStatus.balanced'), not_determinable: t('balance.balanceStatus.not_determinable') },
    analysisStatus: { ok: t('balance.status.ok'), partial: t('balance.status.partial'), not_available: t('balance.status.not_available') },
    studyStatus: { idle: t('workspace.study.status.idle'), connecting: t('workspace.study.status.connecting'), running: t('workspace.study.status.running'),
      completed: t('workspace.study.status.completed'), cancelled: t('workspace.study.status.cancelled'), failed: t('workspace.study.status.failed'),
      none: t('workspace.study.status.none') },
    priority: { high: t('balance.priority.high'), medium: t('balance.priority.medium'), low: t('balance.priority.low'), conditional: t('balance.priority.conditional') },
    horizon: { short: t('balance.horizon.short'), medium: t('balance.horizon.medium'), long: t('balance.horizon.long') },
    nature: { recommendation: t('balance.nature.recommendation'), data_improvement: t('balance.nature.data_improvement'),
      conditional_option: t('balance.nature.conditional_option'), scenario: t('results.nature.scenario') },
    option: Object.fromEntries(OPTION_KINDS.map((o) => [o, t(`balance.option.${o}`)])),
    studyRecommendation: t('results.studyRecommendation'),
    notQuantified: t('balance.notQuantified'),
  }), [t]);
}

/**
 * The assistant workspace. Right (desktop): the conversation with Al Mulhim or Ilham. Left: the
 * persona's portrait with only its name, state, service status, persona choice and audio
 * controls; "Run analysis" with questions for the chosen sector; and the results of the latest
 * analysis or assistant study, in tabs (summary, tables, charts, sources, recommendations).
 * A question passed as ?q= is prefilled, not sent; ?analysis= opens a stored analysis.
 */
export function AssistantPage() {
  const { t } = useTranslation();
  const language = useAppLanguage();
  const { persona } = usePersona();
  const name = persona.name[language];
  const to = usePreservedSearch();
  const [params] = useSearchParams();
  const question = (params.get('q') ?? '').slice(0, 1000);
  const [mode] = useDataMode();
  const ui = useAssistantUi();
  const status = useAssistantStatus();
  const voiceStatus = useVoiceStatus();
  const labels = useResultLabels();
  const askRef = useRef<AskFromOutside | null>(null);
  const formId = useId();

  const [sector, setSectorState] = useState<Sector>(readSector);
  const setSector = (s: Sector) => {
    setSectorState(s);
    try { window.localStorage.setItem(SECTOR_KEY, s); } catch { /* storage blocked: kept for this visit */ }
  };
  const [periodKind, setPeriodKind] = useState<'annual' | 'year_to_date'>('annual');
  const [supply, setSupply] = useState('');
  const [demand, setDemand] = useState('');
  const [years, setYears] = useState('');
  const configured = Boolean(status.data?.configured);
  const [explain, setExplain] = useState(true);

  const run = useRunBalance();
  const [analysisId, setAnalysisId] = useState<string | null>(() => params.get('analysis'));
  const stored = useBalance(analysisId);
  const active = ui.activeStudy;
  const study = useLiveStudy(active?.id ?? null, active?.guest ?? false, active?.epoch ?? 0);
  const [view, setView] = useState<'analysis' | 'study'>(analysisId ? 'analysis' : 'study');
  // A new study started from the conversation brings its results forward, except the
  // explanation requested together with an analysis (the analysis stays in front).
  const [keepAnalysis, setKeepAnalysis] = useState(false);
  const [shownStudy, setShownStudy] = useState(active?.id ?? null);
  if ((active?.id ?? null) !== shownStudy) {
    // Adjusting state while rendering (React docs pattern), instead of an effect.
    setShownStudy(active?.id ?? null);
    if (active && !keepAnalysis) setView('study');
    setKeepAnalysis(false);
  }

  const scenarioGiven = supply.trim() !== '' || demand.trim() !== '' || years.trim() !== '';
  const runAnalysis = () => {
    run.mutate(
      {
        data_mode: mode,
        params: {
          sector, period_kind: periodKind,
          ...(scenarioGiven ? { supply_growth_pct: supply.trim(), demand_growth_pct: demand.trim(), years: Number(years) } : {}),
        },
      },
      {
        onSuccess: (result) => {
          setAnalysisId(result.id);
          setView('analysis');
          if (explain && configured && askRef.current) {
            setKeepAnalysis(true);
            askRef.current(t(`assistantPage.questions.${sector}.q1`), 'analyze');
          }
        },
      },
    );
  };

  const balanceModel = stored.data ? fromBalance(stored.data, language, labels) : null;
  const studyModel = active && study.status !== 'idle' ? fromStudy(study, { id: active.id, question: active.question }, language, labels) : null;
  const model = view === 'analysis' ? (balanceModel ?? studyModel) : (studyModel ?? balanceModel);

  // Listening: a stored analysis is read by the server voice when configured (its summary, not
  // every cell), else by a browser voice labelled as such; a study plays its narration.
  const serverVoice = Boolean(voiceStatus.data?.configured);
  const completion = study.completion;
  const segments = useMemo(() => completion?.narration ?? [], [completion]);
  const narration = useNarration({
    segments,
    messageId: study.completion?.message_id ?? null,
    language: (study.completion?.language ?? language),
    gender: persona.gender,
    serverSpeech: serverVoice,
  });
  const [listening, setListening] = useState(false);
  // The words being read, shown beside the player.
  const [transcript, setTranscript] = useState<string | null>(null);
  const listenAnalysis = () => {
    if (!stored.data) return;
    setListening(true);
    if (serverVoice) {
      spokenText(stored.data.id, language).then(setTranscript).catch(() => setTranscript(null));
      speakAnalysis(stored.data.id, persona.code, language)
        .then((audio) => {
          playAudio(audio, { onStart: () => undefined, onLevel: () => undefined, onEnd: () => setListening(false), onError: () => setListening(false) });
        })
        .catch(() => setListening(false));
      return;
    }
    const a = stored.data.analysis;
    const text = [a.title[language], ...a.summary.map((s) => s[language]), ...a.balances.map((b) => `${b.title[language]}: ${b.status_label[language]}.`)].join(' ');
    setTranscript(text);
    if (!speak(text, language, persona.gender, { onStart: () => undefined, onEnd: () => setListening(false), onError: () => setListening(false) })) setListening(false);
  };
  const canBrowserSpeak = voiceFor(language, persona.gender) !== null;
  // The analysis, the voice service and the results need the OSRIP API; without it (the mock
  // data adapter) only the conversation is shown, as before.
  const api = adapterKind === 'http';

  // Wide screens (1280 px and up): the identity and the results on the left, the conversation
  // on the right, in both
  // languages (the grid keeps physical sides; each part keeps the page's own direction). The
  // conversation is full height and sticky, with its composer always at the bottom, so the
  // page and the conversation never scroll inside one another. Narrower screens: identity,
  // conversation, then results, one after another.
  const dir = language === 'ar' ? 'rtl' : 'ltr';
  const conversation = (
    <section className={api
      ? 'flex h-[min(44rem,calc(100dvh-8rem))] min-h-[28rem] flex-col overflow-hidden rounded-lg border border-border bg-card max-sm:h-auto xl:sticky xl:top-20 xl:h-[calc(100dvh-7rem)] xl:[grid-area:chat]'
      : 'flex h-[min(40rem,calc(100dvh-10rem))] min-h-[26rem] flex-col overflow-hidden rounded-lg border border-border bg-card'}
      dir={dir} aria-labelledby={`${formId}-conversation`} data-testid="conversation-panel">
      <h2 id={`${formId}-conversation`} className="sr-only">{t('assistantPage.conversation')}</h2>
      <AssistantChat initialDraft={question} askRef={askRef} showIdentity={!api} />
    </section>
  );

  return (
    <>
      <PageHeader title={t('assistant.title', { name })}>
        <div className="mt-1 flex flex-wrap gap-2">
          <Link to={to('/talk')} data-testid="open-talk"
            className="inline-flex w-fit items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary-hover">
            <Mic aria-hidden="true" className="size-4" />{t('talk.open', { name })}
          </Link>
          {api ? (
            <Link to={to(`/studies?create=${sector}`)} data-testid="open-create-study"
              className="inline-flex w-fit items-center gap-2 rounded-md border border-border-strong/60 px-4 py-2 text-sm font-medium hover:bg-muted">
              <FlaskConical aria-hidden="true" className="size-4" />{t('jobs.create')}
            </Link>
          ) : null}
        </div>
      </PageHeader>

      {!api ? <div className="mt-4" data-testid="assistant-workspace">{conversation}</div> : (
        <div data-testid="assistant-workspace" data-layout="conversation-right"
          className="mt-4 flex flex-col gap-4 xl:grid xl:grid-cols-[minmax(0,1fr)_minmax(24rem,34rem)] xl:grid-rows-[auto_1fr] xl:items-start xl:gap-5 xl:[direction:ltr] xl:[grid-template-areas:'identity_chat'_'results_chat']">
          <div className="min-w-0 xl:[grid-area:identity]" dir={dir}>
            <AssistantIdentityCard study={active ? study : null} analysing={run.isPending} failed={run.isError} />
          </div>

          {conversation}

          <section className="flex min-w-0 flex-col gap-4 xl:[grid-area:results]" dir={dir} aria-label={t('results.heading')}>
            <form className="flex flex-col gap-3 rounded-lg border border-border bg-card p-3" data-testid="analysis-form"
              onSubmit={(e) => { e.preventDefault(); runAnalysis(); }} aria-labelledby={`${formId}-analysis`}>
              <h3 id={`${formId}-analysis`} className="flex items-center gap-1.5 text-sm font-semibold"><Sigma aria-hidden="true" className="size-4" />{t('balance.heading')}</h3>
              <div className="flex flex-wrap items-end gap-3">
                <SelectField label={t('balance.sector')} value={sector} onValueChange={(v) => setSector(v as Sector)} data-testid="sector-select"
                  options={SECTORS.map((s) => ({ value: s, label: t(`balance.sectors.${s}`) }))} />
                <Segmented label={t('balance.periodKind')} value={periodKind} onChange={(v) => setPeriodKind(v === 'year_to_date' ? 'year_to_date' : 'annual')}
                  options={[{ value: 'annual', label: t('balance.annual') }, { value: 'year_to_date', label: t('balance.yearToDate') }]} testId="period-kind" />
                <Button type="submit" disabled={run.isPending} data-testid="run-analysis" className="w-fit">
                  <Play aria-hidden="true" />{run.isPending ? t('balance.running') : t('balance.run')}
                </Button>
              </div>
              <details className="text-sm" data-testid="scenario-inputs">
                <summary className="cursor-pointer font-medium">{t('balance.scenario')}</summary>
                <p className="mt-1 text-xs text-muted-foreground">{t('balance.scenarioHint')}</p>
                <div className="mt-2 grid gap-2 sm:grid-cols-3">
                  {([[t('balance.supplyGrowth'), supply, setSupply, 'scenario-supply'], [t('balance.demandGrowth'), demand, setDemand, 'scenario-demand'],
                    [t('balance.years'), years, setYears, 'scenario-years']] as const).map(([label, value, set, id]) => (
                    <div key={id} className="flex flex-col gap-1 text-xs font-medium">
                      <label htmlFor={`${formId}-${id}`}>{label}</label>
                      <input id={`${formId}-${id}`} type="number" inputMode="decimal" step="any" value={value} onChange={(e) => set(e.target.value)} data-testid={id}
                        min={id === 'scenario-years' ? 1 : -50} max={id === 'scenario-years' ? 10 : 50}
                        className="h-9 rounded-md border border-border-strong bg-card px-2 text-sm" dir="ltr" />
                    </div>
                  ))}
                </div>
              </details>
              {configured ? (
                <label className="flex items-start gap-2 text-xs font-medium" title={t('balance.explainNote')}>
                  <input type="checkbox" checked={explain} onChange={(e) => setExplain(e.target.checked)} className="mt-0.5 size-4 accent-primary"
                    data-testid="analysis-explain" />
                  {t('balance.explain', { name })}
                </label>
              ) : status.data ? (
                <p className="text-xs text-muted-foreground" data-testid="analysis-explain-unavailable">{t('balance.explainUnavailable')}</p>
              ) : null}
              {run.isError ? <p className="text-sm text-destructive" role="alert" data-testid="analysis-error">{t('balance.failed', { message: run.error.message })}</p> : null}
              <div className="flex flex-col gap-1.5 border-t border-border pt-2" data-testid="sector-suggestions" data-sector={sector}>
                <p className="text-xs font-semibold">{t('assistantPage.suggestions', { sector: t(`balance.sectors.${sector}`) })}</p>
                <div className="flex flex-wrap gap-1.5">
                  {(['q1', 'q2', 'q3'] as const).map((q) => {
                    const text = t(`assistantPage.questions.${sector}.${q}`);
                    return (
                      <button key={q} type="button" onClick={() => askRef.current?.(text)} dir="auto" data-testid="sector-question"
                        className="rounded-full border border-border-strong/50 px-3 py-1.5 text-start text-xs transition-colors hover:bg-muted motion-reduce:transition-none focus-visible:outline-2 focus-visible:outline-ring">
                        {text}
                      </button>
                    );
                  })}
                </div>
              </div>
            </form>

            <div className="flex min-w-0 flex-col gap-3 rounded-lg border border-border bg-card p-4" data-testid="results-area">
              {balanceModel && studyModel ? (
                <Segmented label={t('results.show')} value={view} onChange={(v) => setView(v === 'analysis' ? 'analysis' : 'study')} testId="results-view"
                  options={[{ value: 'analysis', label: t('results.fromAnalysis') }, { value: 'study', label: t('results.fromStudy') }]} />
              ) : null}
              {model ? (
                <ResultsPanel model={model} transcript={model.kind === 'balance' ? transcript : null}
                  onListen={model.kind === 'balance'
                    ? (serverVoice || canBrowserSpeak ? listenAnalysis : undefined)
                    : (narration.mode !== 'manual' && (study.completion?.narration.length ?? 0) > 0 ? narration.play : undefined)}
                  listenLabel={model.kind === 'balance' && !serverVoice ? t('balance.listenBrowser') : undefined}
                  listening={model.kind === 'balance' ? listening : narration.playing} />
              ) : stored.isPending && analysisId ? (
                <p className="text-sm text-muted-foreground" role="status">{t('balance.running')}</p>
              ) : (
                <p className="text-sm text-muted-foreground" data-testid="results-empty">{t('results.empty')}</p>
              )}
            </div>
          </section>
        </div>
      )}
    </>
  );
}
