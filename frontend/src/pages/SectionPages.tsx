import { useTranslation } from 'react-i18next';

import { CommodityRegistry } from '@/components/common/CommodityRegistry';
import { PageHeader } from '@/components/common/PageHeader';
import { SectionView } from '@/components/common/SectionView';
import { useDocumentTitle } from '@/lib/useDocumentTitle';

export function ElectricityPage() {
  const { t } = useTranslation();
  useDocumentTitle(t('pages.electricity.title'));
  return (
    <section aria-labelledby="electricity-heading">
      <h2 id="electricity-heading" className="mb-1 text-xl font-semibold">{t('pages.electricity.title')}</h2>
      <p className="mb-6 max-w-3xl text-sm text-muted-foreground">{t('pages.electricity.intro')}</p>
      <SectionView section="electricity" filters={['indicator']} title={t('pages.electricity.title')} headingLevel={3} />
    </section>
  );
}

export function WaterPage() {
  const { t } = useTranslation();
  useDocumentTitle(t('pages.water.title'));
  return (
    <section aria-labelledby="water-heading">
      <h2 id="water-heading" className="mb-1 text-xl font-semibold">{t('pages.water.title')}</h2>
      <p className="mb-6 max-w-3xl text-sm text-muted-foreground">{t('pages.water.intro')}</p>
      <SectionView section="water" filters={['indicator']} title={t('pages.water.title')} headingLevel={3} />
    </section>
  );
}

export function FoodSecurityPage() {
  const { t } = useTranslation();
  return (
    <>
      <PageHeader title={t('pages.food.title')} intro={t('pages.food.intro')} illustration="food" />
      <div className="mb-6">
        <CommodityRegistry />
      </div>
      <SectionView section="food_security" filters={['commodity', 'indicator', 'flow']} title={t('pages.food.title')} />
    </>
  );
}

export function TradePage() {
  const { t } = useTranslation();
  return (
    <>
      <PageHeader title={t('pages.trade.title')} intro={t('pages.trade.intro')} illustration="trade" />
      <div className="mb-6">
        <CommodityRegistry />
      </div>
      <SectionView section="trade" filters={['indicator', 'flow', 'partner', 'commodity']} title={t('pages.trade.title')} />
    </>
  );
}
