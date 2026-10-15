import { Eye, EyeOff } from 'lucide-react';
import { Link } from 'react-router';
import { useTranslation } from 'react-i18next';

import { useMe } from '@/api/auth';
import { adapterKind } from '@/api/config';
import { useUnwatch, useWatch, useWatchlist } from '@/api/library';
import { Button } from '@/components/ui/button';
import type { Series } from '@/domain/types';
import { usePreservedSearch } from '@/state/usePreservedSearch';

/** Adds one series (indicator, area, period kind, data mode) to the reader's watchlist.
 * Partner and commodity breakdowns are not watchable: alerts cover headline series only. */
export function WatchButton({ series }: { series: Series }) {
  const { t } = useTranslation();
  const me = useMe();
  const signedIn = Boolean(me.data?.authenticated) && !me.data?.password_change_required;
  const watchlist = useWatchlist(signedIn);
  const watch = useWatch();
  const unwatch = useUnwatch();
  const to = usePreservedSearch();
  if (adapterKind !== 'http' || !signedIn || series.partnerCode || series.commodityCode || !series.frequency) return null;
  const area = series.area?.code ?? 'OM';
  const existing = watchlist.data?.find((w) => w.indicator.code === series.indicatorCode && w.area.code === area
    && w.period_kind === series.frequency && w.data_mode === series.dataMode);
  const busy = watch.isPending || unwatch.isPending || watchlist.isPending;
  const target = to('/library');
  return (
    <span className="inline-flex flex-wrap items-center gap-2">
      {existing ? (
        <>
          <Link to={{ pathname: target.pathname, search: `${target.search ? `${target.search}&` : '?'}tab=watch` }}
            className="text-primary underline underline-offset-2" data-testid="watching">{t('library.watching')}</Link>
          <Button size="sm" variant="ghost" disabled={busy} onClick={() => unwatch.mutate(existing.id)} aria-label={t('library.unwatch')}>
            <EyeOff aria-hidden="true" />
          </Button>
        </>
      ) : (
        <Button size="sm" variant="outline" disabled={busy} data-testid="watch-series"
          onClick={() => watch.mutate({ indicator: series.indicatorCode, area, period_kind: series.frequency ?? 'annual', data_mode: series.dataMode })}>
          <Eye aria-hidden="true" />{t('library.watch')}
        </Button>
      )}
      {watch.error ? <span className="text-destructive" role="alert">{t('library.watchFailed', { message: watch.error.message })}</span> : null}
    </span>
  );
}
