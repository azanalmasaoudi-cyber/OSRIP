import { useTranslation } from 'react-i18next';

import { CrossfadeImage } from './EditorialImage';
import type { EditorialId } from '@/content/editorial.generated';
import { cn } from '@/lib/utils';

export type Sector = 'electricity' | 'water' | 'food' | 'trade';

const SIZE = { width: 320, height: 240 } as const;

/** Sectors with a raster editorial illustration (see the asset manifest); food has none yet. */
const RASTER: Partial<Record<Sector, EditorialId>> = {
  electricity: 'electricity',
  water: 'water',
  trade: 'trade',
};

/**
 * Sector illustration beside a page title. Raster editorial illustrations (responsive
 * AVIF/WebP/JPEG, documented in the asset manifest) where one exists, otherwise the
 * original SVG drawn for OSRIP. Each carries a visible "Illustration" label so it is
 * never mistaken for a photograph of a real site; switching sector crossfades.
 */
export function SectorIllustration({ sector, className, eager = false }: { sector: Sector; className?: string; eager?: boolean }) {
  const { t } = useTranslation();
  const raster = RASTER[sector];
  return (
    <figure className={cn('relative m-0 overflow-hidden rounded-lg', className)} data-testid="sector-illustration" data-sector={sector}>
      {raster ? (
        <CrossfadeImage id={raster} alt={t(`illustrations.${sector}`)} sizes="(min-width: 1024px) 16rem, 12rem" eager={eager} />
      ) : (
        <img src={`/images/illustrations/sector-${sector}.svg`} width={SIZE.width} height={SIZE.height}
          alt={t(`illustrations.${sector}`)} loading={eager ? 'eager' : 'lazy'} decoding="async" className="h-auto w-full" />
      )}
      <figcaption className="absolute end-2 bottom-2 rounded-sm bg-black/55 px-1.5 py-0.5 text-[0.65rem] font-medium text-white">
        {t('illustrations.label')}
      </figcaption>
    </figure>
  );
}
