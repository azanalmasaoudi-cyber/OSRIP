import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';

import { DEFAULT_LANGUAGE, directionFor, isAppLanguage, readStoredLanguage, storeLanguage } from './languages';
import { ar } from './locales/ar';
import { en } from './locales/en';

const initialLanguage = readStoredLanguage() ?? DEFAULT_LANGUAGE;

function applyDocumentLanguage(language: string): void {
  if (!isAppLanguage(language)) return;
  document.documentElement.lang = language;
  document.documentElement.dir = directionFor(language);
}

void i18n.use(initReactI18next).init({
  resources: { en: { translation: en }, ar: { translation: ar } },
  lng: initialLanguage,
  fallbackLng: DEFAULT_LANGUAGE,
  supportedLngs: ['en', 'ar'],
  interpolation: { escapeValue: false }, // React already escapes output
});

applyDocumentLanguage(initialLanguage);

// Switching language changes labels and direction only. Query state (data mode,
// filters) lives in the URL and is untouched (booklet UX01 / T08).
i18n.on('languageChanged', (language) => {
  applyDocumentLanguage(language);
  if (isAppLanguage(language)) storeLanguage(language);
});

export default i18n;
