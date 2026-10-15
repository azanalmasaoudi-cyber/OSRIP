import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { CrenellationDivider } from '@/components/brand/BrandMark';
import { DataModeBadge } from '@/components/common/DataModeBadge';
import { DemoLabel } from '@/components/common/DemoLabel';
import { IndicatorCard } from '@/components/common/IndicatorCard';
import { PageHeader } from '@/components/common/PageHeader';
import { StatePanel, type StateKind } from '@/components/common/StatePanel';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Dialog } from '@/components/ui/dialog';
import type { Series } from '@/domain/types';

/** Token name -> CSS variable; values come from index.css, so this page never drifts. */
const SWATCHES = [
  ['background', 'Ivory page'],
  ['card', 'Card surface'],
  ['muted', 'Sunken surface'],
  ['foreground', 'Ink'],
  ['muted-foreground', 'Secondary ink'],
  ['primary', 'Deep green'],
  ['nav', 'Navigation green'],
  ['accent', 'Burgundy accent'],
  ['sand', 'Sand'],
  ['sand-subtle', 'Sand, subtle'],
  ['destructive', 'Error'],
  ['chart-1', 'Chart mark'],
] as const;

const STATES: readonly StateKind[] = ['loading', 'empty', 'no_verified_data', 'error', 'not_implemented', 'restricted'];

/**
 * DEMONSTRATION CONTENT: an invented series used only to render the indicator
 * card on this page. Synthetic mode, no publisher, arbitrary placeholder years.
 */
const SAMPLE_SERIES: Series = {
  indicatorCode: 'REFERENCE_SAMPLE',
  section: 'electricity',
  name: { en: 'Sample indicator (demonstration)', ar: 'مؤشر نموذجي (توضيحي)' },
  definition: { en: 'Invented values that exist only to show the component.', ar: 'قيم مخترعة لعرض المكوّن فقط.' },
  unit: { code: 'unit', label: { en: 'units', ar: 'وحدة' } },
  valueType: 'period_total',
  commodityCode: null,
  flow: null,
  partnerCode: null,
  dataMode: 'synthetic',
  source: { title: 'Interface reference sample (synthetic)', publisher: null, url: null, versionLabel: 'demo', accessDate: null },
  note: { en: 'Demonstration content. Not data.', ar: 'محتوى توضيحي، وليس بيانات.' },
  observations: [
    { periodStart: '2001-01-01', periodEnd: '2001-12-31', periodComplete: true, value: '1200', qualityStatus: 'accepted', sourceRow: 'demo:1' },
    { periodStart: '2002-01-01', periodEnd: '2002-12-31', periodComplete: true, value: '1350.5', qualityStatus: 'accepted', sourceRow: 'demo:2' },
  ],
};

export function DesignReferencePage() {
  const { t } = useTranslation();
  const [dialogOpen, setDialogOpen] = useState(false);

  return (
    <>
      <PageHeader title={t('pages.design.title')} intro={t('pages.design.intro')}>
        <div>
          <DemoLabel />
        </div>
      </PageHeader>

      <div className="flex flex-col gap-12">
        <section aria-labelledby="ref-colours">
          <h2 id="ref-colours" className="mb-4 text-xl font-semibold">{t('pages.design.coloursHeading')}</h2>
          <ul className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4" dir="ltr">
            {SWATCHES.map(([token, name]) => (
              <li key={token} className="overflow-hidden rounded-lg border border-border bg-card">
                <div className="h-14 border-b border-border" style={{ background: `var(--${token})` }} />
                <p className="px-3 pt-2 text-sm font-medium">{name}</p>
                <p className="px-3 pb-2 font-mono text-xs text-muted-foreground">--{token}</p>
              </li>
            ))}
          </ul>
        </section>

        <section aria-labelledby="ref-type">
          <h2 id="ref-type" className="mb-4 text-xl font-semibold">{t('pages.design.typeHeading')}</h2>
          <div className="grid gap-4 md:grid-cols-2">
            {(['en', 'ar'] as const).map((lng) => (
              <div key={lng} lang={lng} dir={lng === 'ar' ? 'rtl' : 'ltr'} className="rounded-lg border border-border bg-card p-5">
                <p className="text-3xl font-semibold">{lng === 'ar' ? 'منصة عُمان الذكية' : 'Oman Smart Resource'}</p>
                <p className="text-xl font-medium">{lng === 'ar' ? 'الطاقة والخدمات الأساسية' : 'Energy and Essential Services'}</p>
                <p className="text-base">{lng === 'ar' ? 'توليد الكهرباء واستهلاك المياه والتجارة.' : 'Electricity generation, water consumption and trade.'}</p>
                <p className="text-sm text-muted-foreground" dir="ltr">0 1 2 3 4 5 6 7 8 9 · 48,000 · 50,100</p>
                <p className="mt-2 font-mono text-xs text-muted-foreground" dir="ltr">
                  {lng === 'ar' ? 'IBM Plex Sans Arabic' : 'IBM Plex Sans'} · 400 / 500 / 600
                </p>
              </div>
            ))}
          </div>
        </section>

        <section aria-labelledby="ref-controls">
          <h2 id="ref-controls" className="mb-4 text-xl font-semibold">{t('pages.design.controlsHeading')}</h2>
          <div className="flex flex-wrap items-center gap-3">
            <Button>{t('pages.design.primaryAction')}</Button>
            <Button variant="outline">{t('pages.design.secondaryAction')}</Button>
            <Button variant="ghost">{t('pages.design.quietAction')}</Button>
            <Button variant="outline" onClick={() => setDialogOpen(true)} data-testid="open-sample-dialog">
              {t('pages.design.openDialog')}
            </Button>
          </div>
          <Dialog open={dialogOpen} onClose={() => setDialogOpen(false)} title={t('pages.design.dialogTitle')}>
            <p className="text-sm">{t('pages.design.dialogBody')}</p>
            <div className="mt-4 flex justify-end">
              <Button onClick={() => setDialogOpen(false)}>{t('dialog.close')}</Button>
            </div>
          </Dialog>
        </section>

        <section aria-labelledby="ref-badges">
          <h2 id="ref-badges" className="mb-4 text-xl font-semibold">{t('pages.design.badgesHeading')}</h2>
          <div className="flex flex-wrap gap-2">
            <DataModeBadge mode="verified_source" />
            <DataModeBadge mode="synthetic" />
            <Badge variant="sand">{t('commodityStatus.provisional')}</Badge>
            <Badge variant="accent">{t('nav.authorizedOnly')}</Badge>
            <Badge variant="muted">{t('quality.withheld')}</Badge>
            <DemoLabel />
            <DemoLabel kind="artwork" />
          </div>
        </section>

        <section aria-labelledby="ref-card">
          <h2 id="ref-card" className="mb-4 text-xl font-semibold">{t('pages.design.cardsHeading')}</h2>
          <div className="max-w-sm">
            <IndicatorCard series={SAMPLE_SERIES} />
          </div>
        </section>

        <section aria-labelledby="ref-states">
          <h2 id="ref-states" className="mb-4 text-xl font-semibold">{t('pages.design.statesHeading')}</h2>
          <div className="grid gap-4 lg:grid-cols-2">
            {STATES.map((kind) => (
              <div key={kind}>
                <p className="mb-2 font-mono text-xs text-muted-foreground" dir="ltr">{kind}</p>
                <StatePanel
                  kind={kind}
                  skeleton="lines"
                  detail={kind === 'error' ? t('pages.design.sampleDetail') : undefined}
                  onRetry={kind === 'error' ? () => undefined : undefined}
                  onReset={kind === 'empty' ? () => undefined : undefined}
                />
              </div>
            ))}
            <div>
              <p className="mb-2 font-mono text-xs text-muted-foreground" dir="ltr">missing value</p>
              <p className="rounded-lg border border-border bg-card p-6 text-sm">
                {t('table.value')}: <span className="italic text-muted-foreground" data-missing="true">{t('states.missingValue')}</span>
              </p>
            </div>
          </div>
        </section>

        <section aria-labelledby="ref-patterns">
          <h2 id="ref-patterns" className="mb-4 text-xl font-semibold">{t('pages.design.patternsHeading')}</h2>
          <div className="grid gap-4 md:grid-cols-2">
            <figure className="m-0 overflow-hidden rounded-lg border border-border bg-card">
              <div className="relative h-32 bg-nav">
                <div aria-hidden="true" className="pattern-lattice absolute inset-0 bg-nav-ring/40" />
              </div>
              <figcaption className="p-3 text-sm">{t('pages.design.patternLattice')}</figcaption>
            </figure>
            <figure className="m-0 overflow-hidden rounded-lg border border-border bg-card">
              <div className="flex h-32 items-end bg-sand-subtle">
                <CrenellationDivider className="h-3.5 bg-sand" />
              </div>
              <figcaption className="p-3 text-sm">{t('pages.design.patternCrenellation')}</figcaption>
            </figure>
          </div>
        </section>
      </div>
    </>
  );
}
