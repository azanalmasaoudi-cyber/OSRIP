import { useTranslation } from 'react-i18next';

import type { Sector } from '@/components/brand/SectorIllustration';
import { SectorImage } from '@/components/brand/SectorImage';
import { CommodityRegistry } from '@/components/common/CommodityRegistry';
import { DecisionBrief } from '@/components/sector/DecisionBrief';
import { SectorNav } from '@/components/sector/SectorNav';
import { SectorWorkflow } from '@/components/sector/SectorWorkflow';
import type { SectionCode } from '@/domain/types';
import { useDocumentTitle } from '@/lib/useDocumentTitle';

/** One sector page: the sector's name and image with the four sectors as tabs (step 1), then the
 * selection, results and insights (components/sector/SectorWorkflow). Results appear only after
 * "Show results"; a chart only after "Show chart". Then the decision brief of the axis. */
function SectorPage({ section, page, image, registry = false }: {
  section: SectionCode;
  page: 'electricity' | 'water' | 'food' | 'trade';
  image: Sector;
  registry?: boolean;
}) {
  const { t } = useTranslation();
  const title = t(`pages.${page}.title`);
  useDocumentTitle(title);
  return (
    <div className="flex flex-col gap-6 lg:gap-8" data-testid="sector-page" data-sector={page}>
      <header className="overflow-hidden rounded-xl border border-border bg-card shadow-card">
        <div className="grid md:grid-cols-[minmax(0,1fr)_minmax(0,0.85fr)]">
          <div className="gold-rule flex flex-col justify-center gap-2 p-5 sm:p-6 lg:p-8">
            <p className="text-sm font-semibold text-primary ltr:tracking-wider ltr:uppercase">{t('sectorFlow.eyebrow')}</p>
            <h1 className="text-2xl leading-tight font-semibold sm:text-3xl 3xl:text-4xl">{title}</h1>
            <p className="max-w-2xl text-base text-muted-foreground">{t(`pages.${page}.lead`)}</p>
          </div>
          <SectorImage sector={image} variant="banner" eager className="max-md:hidden" />
        </div>
        <SectorNav />
      </header>
      <SectorWorkflow section={section} title={title} />
      <DecisionBrief section={section} />
      {registry ? (
        <details className="rounded-lg border border-border bg-card p-4 shadow-card" data-testid="commodity-registry-details">
          <summary className="cursor-pointer text-base font-semibold">{t('pages.food.commoditiesHeading')}</summary>
          <div className="mt-3"><CommodityRegistry /></div>
        </details>
      ) : null}
    </div>
  );
}

export function ElectricityPage() {
  return <SectorPage section="electricity" page="electricity" image="electricity" />;
}

export function WaterPage() {
  return <SectorPage section="water" page="water" image="water" />;
}

export function FoodSecurityPage() {
  return <SectorPage section="food_security" page="food" image="food" registry />;
}

export function TradePage() {
  return <SectorPage section="trade" page="trade" image="trade" registry />;
}
