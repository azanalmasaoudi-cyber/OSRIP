import { useQueryClient } from '@tanstack/react-query';
import { DatabaseZap, FlaskConical, RotateCcw, ServerOff, ShieldCheck, Unplug } from 'lucide-react';
import { useEffect, useRef } from 'react';
import { useTranslation } from 'react-i18next';

import { adapterKind } from '@/api/config';
import { useServerConnection } from '@/api/monitoring';
import { problemOf } from '@/api/problems';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { useDataMode } from '@/state/useDataMode';

type ConnectionProblem = 'not_connected' | 'server_unavailable' | 'database_unavailable' | 'database_not_ready';
const CONNECTION_ICON = { not_connected: Unplug, server_unavailable: ServerOff, database_unavailable: DatabaseZap, database_not_ready: DatabaseZap };

/**
 * One plain statement, on every page, when this site cannot reach a working OSRIP server: no API at
 * this address (a static host such as Vercel serving only the interface), the server not
 * responding, or its database unavailable or not migrated. Pages then explain their own empty
 * panels the same way. "Try again" asks the server and then every page query again; when the
 * server comes back by itself, the pages reload their data too.
 */
export function ConnectionBanner() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const connection = useServerConnection();
  let problem: ConnectionProblem | null = null;
  if (connection.isError) {
    const kind = problemOf(connection.error).kind;
    if (kind === 'not_connected' || kind === 'server_unavailable' || kind === 'database_unavailable') problem = kind;
    else if (kind === 'invalid_response' || kind === 'request_failed') problem = 'server_unavailable';
  } else if (connection.data && !connection.data.ready) {
    problem = connection.data.database === 'ok' ? 'database_not_ready' : 'database_unavailable';
  }
  // Back to normal after a problem: reload what the pages failed to load.
  const hadProblem = useRef(false);
  useEffect(() => {
    if (problem) hadProblem.current = true;
    else if (hadProblem.current && connection.data?.ready) {
      hadProblem.current = false;
      void queryClient.invalidateQueries();
    }
  }, [problem, connection.data?.ready, queryClient]);

  if (adapterKind !== 'http' || !problem) return null;
  const Icon = CONNECTION_ICON[problem];
  return (
    <div role="alert" className="border-b border-destructive/40 bg-destructive/5" data-testid="connection-banner" data-problem={problem}>
      <div className="mx-auto flex max-w-[var(--content-max)] flex-wrap items-start gap-x-3 gap-y-2 px-4 py-2.5 text-sm sm:px-6 lg:px-8">
        <Icon aria-hidden="true" className="mt-0.5 size-4 shrink-0 text-destructive" />
        <p className="min-w-0 flex-1">
          <span className="font-semibold text-destructive">{t(`problems.${problem}.title`)}.</span>{' '}
          <span className="text-muted-foreground">{t(`problems.${problem}.body`)}</span>
        </p>
        <Button type="button" variant="outline" size="sm" className="h-7" disabled={connection.isFetching}
          onClick={() => void queryClient.invalidateQueries()} data-testid="connection-retry">
          <RotateCcw aria-hidden="true" />{t('states.retry')}
        </Button>
      </div>
    </div>
  );
}

/** A persistent statement of what the user is looking at, in one slim strip: the data mode, with
 * what it means. Technical details (the API address, the offline prototype, the services) are
 * listed under Settings › Services instead. */
export function StatusBanners() {
  const { t } = useTranslation();
  const [mode] = useDataMode();
  const ModeIcon = mode === 'synthetic' ? FlaskConical : ShieldCheck;

  return (
    <div className="border-b border-border bg-card/60">
      <div className="mx-auto flex max-w-[var(--content-max)] flex-wrap items-center gap-x-4 gap-y-1.5 px-4 py-2 text-xs sm:px-6 lg:px-8">
        <p
          role="status"
          data-testid="data-mode-banner"
          data-mode={mode}
          className={cn(
            'inline-flex min-w-0 items-start gap-1.5 rounded-md border px-2 py-1 font-medium',
            mode === 'synthetic'
              ? 'border-synthetic-border/70 bg-synthetic text-synthetic-foreground'
              : 'border-verified-border/70 bg-verified text-verified-foreground',
          )}
        >
          <ModeIcon aria-hidden="true" className="mt-px size-3.5 shrink-0" />
          {mode === 'synthetic' ? t('dataMode.syntheticBanner') : t('dataMode.verifiedBanner')}
        </p>
      </div>
    </div>
  );
}
