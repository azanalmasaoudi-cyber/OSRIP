import { useState, type ImgHTMLAttributes } from 'react';
import { useTranslation } from 'react-i18next';

// A neutral "AI" badge in the brand emerald (white on #0b6a4c: contrast 6.6:1, in both themes).
const FALLBACK_SRC = `data:image/svg+xml,${encodeURIComponent(
  '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><rect width="100" height="100" fill="#0b6a4c"/>'
  + '<text x="50" y="50" dy=".35em" text-anchor="middle" font-family="system-ui,sans-serif" font-size="34" font-weight="700" fill="#fff">AI</text></svg>',
)}`;

/**
 * A persona portrait that never shows as a broken image. When it cannot be loaded (for example
 * a copy shared without Ilham's portrait), a neutral "AI" badge takes its place in the same box,
 * with the same size and shape, and the conversation carries on. The badge is not anyone's
 * likeness. A new source is tried again.
 */
export function PersonaImage({ src, alt = '', ...props }: ImgHTMLAttributes<HTMLImageElement>) {
  const { t } = useTranslation();
  const [failedSource, setFailedSource] = useState<string>();
  if (!src || failedSource === src) {
    return <img {...props} src={FALLBACK_SRC} alt={alt ? t('assistant.aiAssistant') : ''} data-testid="persona-image-fallback" />;
  }
  return <img {...props} src={src} alt={alt} onError={() => setFailedSource(src)} />;
}
