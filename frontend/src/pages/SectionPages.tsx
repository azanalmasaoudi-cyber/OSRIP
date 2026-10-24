import { useTranslation } from 'react-i18next';

import type { Sector } from '@/components/brand/SectorIllustration';
import { CommodityRegistry } from '@/components/common/CommodityRegistry';
import { PageHeader } from '@/components/common/PageHeader';
import { SectorNav } from '@/components/sector/SectorNav';
import { SectorWorkflow } from '@/components/sector/SectorWorkflow';
import type { SectionCode } from '@/domain/types';

/** One sector page: what the sector covers, the four sectors, then the period-first
 * selection; results appear only after "Show results" (components/sector/SectorWorkflow). */
function SectorPage({ section, page, illustration, registry = false }: {
  section: SectionCode;
  page: 'electricity' | 'water' | 'food' | 'trade';
  illustration: Sector;
  registry?: boolean;
}) {
  const { t } = useTranslation();
  const title = t(`pages.${page}.title`);
  return (
    <>
      <PageHeader title={title} intro={t(`pages.${page}.intro`)} illustration={illustration} />
      <SectorNav />
      <SectorWorkflow section={section} title={title} />
      {registry ? (
        <details className="mt-6 rounded-lg border border-border bg-card p-4" data-testid="commodity-registry-details">
          <summary className="cursor-pointer text-sm font-semibold">{t('pages.food.commoditiesHeading')}</summary>
          <div className="mt-3"><CommodityRegistry /></div>
        </details>
      ) : null}
    </>
  );
}

export function ElectricityPage() {
  return <SectorPage section="electricity" page="electricity" illustration="electricity" />;
}

export function WaterPage() {
  return <SectorPage section="water" page="water" illustration="water" />;
}

export function FoodSecurityPage() {
  return <SectorPage section="food_security" page="food" illustration="food" registry />;
}

export function TradePage() {
  return <SectorPage section="trade" page="trade" illustration="trade" registry />;
}
