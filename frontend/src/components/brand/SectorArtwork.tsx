import { useTranslation } from 'react-i18next';

import type { Sector } from './SectorIllustration';
import { cn } from '@/lib/utils';

/*
 * The four sector artworks supplied for OSRIP (AI-generated illustrations, each with its own
 * Arabic and English title; public/images/sectors). Each is shown whole at its own 1672 × 941
 * ratio: never cropped, stretched or covered with text. Browsers that read WebP get a copy at
 * the width they need (836 or 1672 pixels); others get the original PNG, which is kept as
 * supplied.
 */

const FILE: Record<Sector, string> = {
  electricity: 'osrip_electricity',
  water: 'osrip_water',
  food: 'osrip_food_security',
  trade: 'osrip_trade',
};

export const SECTOR_ART_SIZE = { width: 1672, height: 941 } as const;

export function SectorArtwork({ sector, sizes, eager = false, className, imageClassName }: {
  sector: Sector;
  /** The displayed width, so the browser picks the smaller copy where it is enough. */
  sizes: string;
  /** At the top of a page: load at once. Elsewhere it loads when it nears the screen. */
  eager?: boolean;
  className?: string;
  imageClassName?: string;
}) {
  const { t } = useTranslation();
  const base = `/images/sectors/${FILE[sector]}`;
  return (
    <picture className={cn('block', className)} data-testid="sector-art" data-sector={sector}>
      <source type="image/webp" srcSet={`${base}-836.webp 836w, ${base}-1672.webp 1672w`} sizes={sizes} />
      <img src={`${base}.png`} width={SECTOR_ART_SIZE.width} height={SECTOR_ART_SIZE.height} alt={t(`sectorArt.${sector}`)}
        loading={eager ? 'eager' : 'lazy'} fetchPriority={eager ? 'high' : 'auto'} decoding="async"
        className={cn('block aspect-[1672/941] h-auto w-full object-contain', imageClassName)} />
    </picture>
  );
}
