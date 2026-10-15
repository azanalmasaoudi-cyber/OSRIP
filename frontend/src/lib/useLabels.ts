import { useTranslation } from 'react-i18next';

import { useAppLanguage } from './useAppLanguage';
import { useCommodities } from '@/api/queries';
import { useDataMode } from '@/state/useDataMode';

/**
 * Display labels for codes that are not UI strings: commodities come from the
 * shared registry; fixture partners (PARTNER_A…) are labelled as fictional.
 * Unknown codes are shown as-is rather than guessed.
 */
export function useCodeLabels() {
  const { t } = useTranslation();
  const language = useAppLanguage();
  const [mode] = useDataMode();
  const commodities = useCommodities(mode);

  const partner = (code: string | null): string => {
    if (code === null) return t('table.allPartners');
    const fictional = /^PARTNER_([A-Z])$/.exec(code);
    return fictional ? t('filters.fictionalPartner', { letter: fictional[1] ?? '' }) : code;
  };

  const commodity = (code: string | null): string => {
    if (code === null) return '';
    return commodities.data?.find((c) => c.code === code)?.name[language] ?? code;
  };

  return { partner, commodity, commodities: commodities.data ?? [] };
}
