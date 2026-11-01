import { useTranslation } from 'react-i18next';

import type { Sector } from './SectorIllustration';
import { PhotoCaption } from '@/components/common/Photo';
import { PHOTOS, type PhotoCredit } from '@/content/photos';
import { useAppLanguage } from '@/lib/useAppLanguage';
import { cn } from '@/lib/utils';

/** Credited photographs of real Omani places (Wikimedia Commons, see content/photos.ts). Electricity
 * has no licensed photograph yet, so it shows the project's own drawing, labelled "Illustration". */
export const SECTOR_PHOTO: Record<Sector, PhotoCredit | null> = {
  electricity: null,
  water: PHOTOS.desalination,
  food: PHOTOS.falaj,
  trade: PHOTOS.duqm,
};

/**
 * One sector's image: a credited photograph (location, creator, licence and a link to the file
 * always visible) or the labelled illustration. `variant="banner"` is a wide strip for page
 * headers; `card` fills the top of a sector card. No movement and no text on the image itself.
 */
export function SectorImage({ sector, variant = 'card', className, eager = false }: {
  sector: Sector;
  variant?: 'banner' | 'card';
  className?: string;
  eager?: boolean;
}) {
  const { t } = useTranslation();
  const language = useAppLanguage();
  const photo = SECTOR_PHOTO[sector];
  // A banner is a fixed-height strip beside the page title from the tablet width up.
  const box = variant === 'banner' ? 'aspect-[16/6] md:aspect-auto md:h-56 3xl:h-64' : 'aspect-[16/9]';
  if (!photo) {
    return (
      <figure className={cn('relative m-0 overflow-hidden bg-sand-subtle', className)} data-testid="sector-image" data-kind="illustration"
        data-sector={sector}>
        <img src={`/images/illustrations/sector-${sector}.svg`} width={320} height={240} alt={t(`illustrations.${sector}`)}
          loading={eager ? 'eager' : 'lazy'} decoding="async" className={cn('block w-full object-contain p-2', box)} />
        <figcaption className="absolute end-2 bottom-2 rounded-sm bg-black/60 px-1.5 py-0.5 text-xs font-medium text-white">
          {t('illustrations.label')}
        </figcaption>
      </figure>
    );
  }
  return (
    <figure className={cn('relative m-0 overflow-hidden', className)} data-testid="photo" data-kind="photo" data-sector={sector}>
      <img src={photo.src} width={photo.width} height={photo.height} alt={photo.alt[language]}
        sizes={variant === 'banner' ? '100vw' : '(min-width: 1280px) 25vw, (min-width: 640px) 50vw, 100vw'}
        loading={eager ? 'eager' : 'lazy'} decoding="async" className={cn('block w-full object-cover', box)} />
      <PhotoCaption photo={photo}
        className="on-nav absolute end-0 bottom-0 max-w-full rounded-ss-md bg-black/65 px-2.5 py-1 text-xs text-white [&_a]:text-white" />
    </figure>
  );
}
