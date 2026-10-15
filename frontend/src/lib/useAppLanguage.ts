import { useTranslation } from 'react-i18next';

import { DEFAULT_LANGUAGE, isAppLanguage } from '@/i18n/languages';
import type { AppLanguage } from './format';

export function useAppLanguage(): AppLanguage {
  const { i18n } = useTranslation();
  return isAppLanguage(i18n.resolvedLanguage) ? i18n.resolvedLanguage : DEFAULT_LANGUAGE;
}
