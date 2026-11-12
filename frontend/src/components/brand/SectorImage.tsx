import type { Sector } from './SectorIllustration';
import { PhotoCaption } from '@/components/common/Photo';
import { PHOTOS, type PhotoCredit } from '@/content/photos';
import { useAppLanguage } from '@/lib/useAppLanguage';
import { cn } from '@/lib/utils';

/**
 * Credited photographs of real Omani places (Wikimedia Commons, see content/photos.ts).
 *
 * Used only on the Overview page. The electricity photograph (pylons in Oman) belongs here and
 * nowhere else: the dashboard cards, the welcome and the sector pages show the sector artworks
 * (SectorArtwork), and the page-header thumbnail shows the labelled illustration (SectorIllustration).
 */
export const SECTOR_PHOTO: Record<Sector, PhotoCredit> = {
  electricity: PHOTOS.pylons,
  water: PHOTOS.desalination,
  food: PHOTOS.falaj,
  trade: PHOTOS.duqm,
};

/**
 * One sector's credited photograph, with its location, creator, licence and a link to the file
 * always visible. `variant="banner"` is a wide strip for page headers; `card` fills the top of a
 * sector card. Cropped to the box (`object-cover`), never stretched; no movement and no text on
 * the image itself. Where WebP copies exist, the browser picks the width it needs.
 */
export function SectorImage({ sector, variant = 'card', className, eager = false }: {
  sector: Sector;
  variant?: 'banner' | 'card';
  className?: string;
  eager?: boolean;
}) {
  const language = useAppLanguage();
  const photo = SECTOR_PHOTO[sector];
  // A banner is a fixed-height strip beside the page title from the tablet width up.
  const box = variant === 'banner' ? 'aspect-[16/6] md:aspect-auto md:h-56 3xl:h-64' : 'aspect-[16/9]';
  const sizes = variant === 'banner' ? '100vw' : '(min-width: 1280px) 25vw, (min-width: 640px) 50vw, 100vw';
  return (
    <figure className={cn('relative m-0 overflow-hidden', className)} data-testid="photo" data-kind="photo" data-sector={sector}>
      <picture>
        {photo.webp ? <source type="image/webp" srcSet={photo.webp} sizes={sizes} /> : null}
        <img src={photo.src} width={photo.width} height={photo.height} alt={photo.alt[language]}
          loading={eager ? 'eager' : 'lazy'} decoding="async" className={cn('block w-full object-cover', box)} />
      </picture>
      <PhotoCaption photo={photo}
        className="on-nav absolute end-0 bottom-0 max-w-full rounded-ss-md bg-black/65 px-2.5 py-1 text-xs text-white [&_a]:text-white" />
    </figure>
  );
}
