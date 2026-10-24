import { FlaskConical, Play, Sigma } from 'lucide-react';
import { useId, useMemo, useRef, useState } from 'react';
import { Link, useSearchParams } from 'react-router';
import { useTranslation } from 'react-i18next';

import { selectionFromParams, speakAnalysis, useAssistantStatus, useVoiceStatus } from '@/api/assistant';
import { OPTION_KINDS, SECTORS, spokenText, useBalance, useRunBalance, type Sector } from '@/api/balance';
import { adapterKind } from '@/api/config';
import { AssistantChat, type AskFromOutside } from '@/components/assistant/AssistantPanel';
import { usePersona } from '@/components/assistant/persona';
import { fromBalance, type Labels } from '@/components/results/model';
import { ResultsPanel } from '@/components/results/ResultsPanel';
import { Button } from '@/components/ui/button';
import { Dialog } from '@/components/ui/dialog';
import { Segmented } from '@/components/ui/segmented';
import { SelectField } from '@/components/ui/select';
import { speak, voiceFor } from '@/lib/speech';
import { useAppLanguage } from '@/lib/useAppLanguage';
import { playAudio } from '@/lib/voicePlayer';
import { useDataMode } from '@/state/useDataMode';
import { usePreservedSearch } from '@/state/usePreservedSearch';

const SECTOR_KEY = 'osrip.assistant.sector';

function readSector(fromUrl: string | null): Sector {
  // A sector page's "Request analysis" link names its sector (?sector=water).
  if ((SECTORS as readonly string[]).includes(fromUrl ?? '')) return fromUrl as Sector;
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
 * The AI Assistant page: one conversation with Al Mulhim or Ilham, centred, filling the
 * window, with the message box at the bottom (components/assistant/ChatView). The shortage and
 * surplus analysis and a full study are optional tools (the Tools drawer), not part of the
 * conversation. A question passed as ?q= is prefilled, not sent; ?sector= chooses the
 * analysis sector; ?analysis= opens a stored analysis.
 */
export function AssistantPage() {
  const { t } = useTranslation();
  const [params] = useSearchParams();
  const question = (params.get('q') ?? '').slice(0, 1000);
  // A question from a sector page carries its applied selection (indicator, area, period).
  const selection = useMemo(() => selectionFromParams(params), [params]);
  const askRef = useRef<AskFromOutside | null>(null);
  const to = usePreservedSearch();
  const api = adapterKind === 'http';
  const [sector, setSector] = useState<Sector>(() => readSector(params.get('sector')));
  const [analysisOpen, setAnalysisOpen] = useState(() => api && Boolean(params.get('analysis')));

  const tools = api ? (
    <section className="flex flex-col gap-2" data-testid="chat-page-tools">
      <Button type="button" variant="outline" className="w-fit" onClick={() => setAnalysisOpen(true)} data-testid="open-analysis" data-close-tools>
        <Sigma aria-hidden="true" />{t('chat.analysisTool')}
      </Button>
      <Link to={to(`/studies?create=${sector}`)} data-testid="open-create-study" data-close-tools
        className="inline-flex w-fit items-center gap-2 rounded-md border border-border-strong/60 px-4 py-2 text-sm font-medium hover:bg-muted">
        <FlaskConical aria-hidden="true" className="size-4" />{t('chat.studyTool')}
      </Link>
    </section>
  ) : undefined;

  return (
    <div className="flex min-h-0 flex-1 flex-col" data-testid="assistant-workspace" data-layout="conversation">
      <AssistantChat variant="chat" initialDraft={question} askRef={askRef} showIdentity={false} selection={selection}
        selectionLabel={selection ? (params.get('sl') ?? '').slice(0, 200) || undefined : undefined} tools={tools} />
      {api ? (
        <Dialog open={analysisOpen} onClose={() => setAnalysisOpen(false)} title={t('balance.heading')} placement="end"
          className="w-[min(44rem,100vw)]">
          <AnalysisTool sector={sector} setSector={setSector} askRef={askRef} onAsked={() => setAnalysisOpen(false)}
            initialId={params.get('analysis')} />
        </Dialog>
      ) : null}
    </div>
  );
}

/** Shortage and surplus analysis (a tool, outside the conversation): run, read, listen, ask. */
function AnalysisTool({ sector, setSector, askRef, onAsked, initialId }: {
  sector: Sector;
  setSector: (s: Sector) => void;
  askRef: { current: AskFromOutside | null };
  onAsked: () => void;
  initialId: string | null;
}) {
  const { t } = useTranslation();
  const language = useAppLanguage();
  const { persona } = usePersona();
  const name = persona.name[language];
  const [mode] = useDataMode();
  const status = useAssistantStatus();
  const voiceStatus = useVoiceStatus();
  const labels = useResultLabels();
  const formId = useId();
  const pickSector = (s: Sector) => {
    setSector(s);
    try { window.localStorage.setItem(SECTOR_KEY, s); } catch { /* storage blocked: kept for this visit */ }
  };
  const [periodKind, setPeriodKind] = useState<'annual' | 'year_to_date'>('annual');
  const [supply, setSupply] = useState('');
  const [demand, setDemand] = useState('');
  const [years, setYears] = useState('');
  const configured = Boolean(status.data?.configured);
  const [explain, setExplain] = useState(true);
  const run = useRunBalance();
  const [analysisId, setAnalysisId] = useState<string | null>(initialId);
  const stored = useBalance(analysisId);
  const ask = (text: string, askMode?: 'analyze') => {
    askRef.current?.(text, askMode);
    onAsked();
  };

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
          // The explanation is asked in the conversation; the analysis stays open here.
          if (explain && configured) askRef.current?.(t(`assistantPage.questions.${sector}.q1`), 'analyze');
        },
      },
    );
  };
  const model = stored.data ? fromBalance(stored.data, language, labels) : null;

  // Listening: read by the server voice when configured (its summary, not every cell), else
  // by a browser voice labelled as such.
  const serverVoice = Boolean(voiceStatus.data?.configured);
  const [listening, setListening] = useState(false);
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

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto px-5 py-4">
      <form className="flex flex-col gap-3" data-testid="analysis-form"
        onSubmit={(e) => { e.preventDefault(); runAnalysis(); }} aria-labelledby={`${formId}-analysis`}>
        <h3 id={`${formId}-analysis`} className="sr-only">{t('balance.heading')}</h3>
        <div className="flex flex-wrap items-end gap-3">
          <SelectField label={t('balance.sector')} value={sector} onValueChange={(v) => pickSector(v as Sector)} data-testid="sector-select"
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
                <button key={q} type="button" onClick={() => ask(text)} dir="auto" data-testid="sector-question"
                  className="rounded-full border border-border-strong/50 px-3 py-1.5 text-start text-xs transition-colors hover:bg-muted motion-reduce:transition-none focus-visible:outline-2 focus-visible:outline-ring">
                  {text}
                </button>
              );
            })}
          </div>
        </div>
      </form>
      <div className="flex min-w-0 flex-col gap-3 border-t border-border pt-4" data-testid="results-area">
        {model ? (
          <ResultsPanel model={model} transcript={transcript}
            onListen={serverVoice || canBrowserSpeak ? listenAnalysis : undefined}
            listenLabel={!serverVoice ? t('balance.listenBrowser') : undefined} listening={listening} />
        ) : stored.isPending && analysisId ? (
          <p className="text-sm text-muted-foreground" role="status">{t('balance.running')}</p>
        ) : (
          <p className="text-sm text-muted-foreground" data-testid="results-empty">{t('results.empty')}</p>
        )}
      </div>
    </div>
  );
}
