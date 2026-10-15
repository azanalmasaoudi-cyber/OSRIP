import { useTranslation } from 'react-i18next';

import { StatePanel } from './StatePanel';
import { DataAdapterError } from '@/api/adapter';
import { useCommodities } from '@/api/queries';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { COMMODITY_STATUS_KEY } from '@/i18n/keys';
import { useAppLanguage } from '@/lib/useAppLanguage';
import { useDataMode } from '@/state/useDataMode';

/** The single commodity registry shared by Food Security and Trade. */
export function CommodityRegistry() {
  const { t } = useTranslation();
  const language = useAppLanguage();
  const [mode] = useDataMode();
  const query = useCommodities(mode);

  return (
    <Card data-testid="commodity-registry">
      <CardHeader>
        <CardTitle>{t('pages.food.commoditiesHeading')}</CardTitle>
        <CardDescription>{t('pages.food.commoditiesNote')}</CardDescription>
      </CardHeader>
      <CardContent>
        {query.isPending ? <StatePanel kind="loading" /> : null}
        {query.isError ? (
          <StatePanel
            kind={query.error instanceof DataAdapterError && query.error.code === 'not_implemented' ? 'not_implemented' : 'error'}
            detail={query.error.message}
          />
        ) : null}
        {query.isSuccess ? (
          <ul className="flex flex-wrap gap-2">
            {query.data.map((commodity) => (
              <li key={commodity.code} className="flex items-center gap-2 rounded-md border border-border px-3 py-1.5 text-sm">
                <span>{commodity.name[language]}</span>
                <Badge variant="muted">{t(COMMODITY_STATUS_KEY[commodity.mappingStatus])}</Badge>
                {commodity.syntheticOnly ? <Badge variant="synthetic">{t('commodityStatus.syntheticOnly')}</Badge> : null}
              </li>
            ))}
          </ul>
        ) : null}
      </CardContent>
    </Card>
  );
}
