import { Zap } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import type { Sector } from './SectorIllustration';
import { PHOTOS } from '@/content/photos';
import { cn } from '@/lib/utils';

/*
 * The sector image on the dashboard cards, the welcome and the sector page headers.
 *
 * Water, food security and trade: the artworks supplied for OSRIP (AI-generated illustrations,
 * each with its own Arabic and English title; public/images/sectors). Each is shown whole at its
 * own 1672 × 941 ratio: never cropped, stretched or covered with text. Browsers that read WebP
 * get a copy at the width they need (836 or 1672 pixels); others get the PNG as supplied.
 *
 * Electricity: a credited photograph of power lines in Oman (content/photos.ts, CC BY-SA 4.0),
 * cropped to the same ratio. The dark frame, the sector's name in both languages and a short
 * credit are laid over it here in the style of the other three; the photograph itself carries no
 * text. The full credit, with links and the changes made, is under Sources → Image credits.
 */

type ArtworkSector = Exclude<Sector, 'electricity'>;

const FILE: Record<ArtworkSector, string> = {
  water: 'osrip_water',
  food: 'osrip_food_security',
  trade: 'osrip_trade',
};

export const SECTOR_ART_SIZE = { width: 1672, height: 941 } as const;

interface SectorArtworkProps {
  sector: Sector;
  /** The displayed width, so the browser picks the smaller copy where it is enough. */
  sizes: string;
  /** At the top of a page: load at once. Elsewhere it loads when it nears the screen. */
  eager?: boolean;
  className?: string;
  imageClassName?: string;
}

export function SectorArtwork({ sector, sizes, eager = false, className, imageClassName }: SectorArtworkProps) {
  const { t } = useTranslation();
  if (sector === 'electricity') {
    return <ElectricityPhoto sizes={sizes} eager={eager} className={className} imageClassName={imageClassName} />;
  }
  const base = `/images/sectors/${FILE[sector]}`;
  return (
    <picture className={cn('block', className)} data-testid="sector-art" data-sector={sector} data-kind="artwork">
      <source type="image/webp" srcSet={`${base}-836.webp 836w, ${base}-1672.webp 1672w`} sizes={sizes} />
      <img src={`${base}.png`} width={SECTOR_ART_SIZE.width} height={SECTOR_ART_SIZE.height} alt={t(`sectorArt.${sector}`)}
        loading={eager ? 'eager' : 'lazy'} fetchPriority={eager ? 'high' : 'auto'} decoding="async"
        className={cn('block aspect-[1672/941] h-auto w-full object-contain', imageClassName)} />
    </picture>
  );
}

/**
 * The electricity photograph in a frame like the other three artworks: a dark outer band, a
 * rounded edge with a warm glow, and the name over the empty sky at the top right, where a dark
 * veil keeps it readable. Sizes follow the card's width (container units), so the layout is the
 * same on a phone and a wide screen. The name is hidden from screen readers because the image's
 * alt text already gives it; the credit is read out.
 */
function ElectricityPhoto({ sizes, eager, className, imageClassName }: Omit<SectorArtworkProps, 'sector'>) {
  const { t } = useTranslation();
  const photo = PHOTOS.pylons;
  return (
    <div className={cn('@container relative block aspect-[1672/941] w-full overflow-hidden bg-[#10131a]', className)}
      data-testid="sector-art" data-sector="electricity" data-kind="photo">
      <div className="absolute inset-[1.4%] overflow-hidden rounded-[3.4cqw] shadow-[0_0_0_1px_rgb(255_214_176/0.65),0_0_18px_rgb(255_160_96/0.45)]">
        <picture>
          <source type="image/webp" srcSet={photo.webp} sizes={sizes} />
          <img src={photo.src} width={photo.width} height={photo.height} alt={t('sectorArt.electricity')}
            loading={eager ? 'eager' : 'lazy'} fetchPriority={eager ? 'high' : 'auto'} decoding="async"
            className={cn('block size-full object-cover object-[45%_50%]', imageClassName)} />
        </picture>
        {/* A warm dusk tint (soft light), so the hazy daylight sits with the other three artworks. */}
        <div aria-hidden="true"
          className="absolute inset-0 bg-[linear-gradient(200deg,rgb(255_168_96/0.75)_0%,rgb(240_120_80/0.35)_45%,rgb(64_48_120/0.55)_100%)] mix-blend-soft-light" />
        <div aria-hidden="true"
          className="absolute inset-0 bg-[linear-gradient(225deg,rgb(36_22_18/0.82)_0%,rgb(36_22_18/0.42)_26%,transparent_52%)]" />
        <div aria-hidden="true" className="absolute inset-x-0 bottom-0 h-[34%] bg-gradient-to-t from-[rgb(9_13_17/0.55)] to-transparent" />
        <div aria-hidden="true" dir="ltr" className="absolute top-[8%] right-[4.5%] flex items-center gap-[2.6cqw]" data-testid="sector-art-title">
          <span className="flex flex-col items-end leading-none [text-shadow:0_2px_14px_rgb(0_0_0/0.5)]">
            <span lang="ar" dir="rtl" className="text-[7.4cqw] font-bold text-white">{t('pages.electricity.title', { lng: 'ar' })}</span>
            <span lang="en" className="mt-[1.4cqw] text-[4.4cqw] font-semibold text-[#f2d9be]">{t('pages.electricity.title', { lng: 'en' })}</span>
          </span>
          <span className="grid size-[12.5cqw] place-items-center rounded-[2.6cqw] border border-[rgb(255_222_196/0.55)] bg-[linear-gradient(145deg,rgb(255_255_255/0.24),rgb(255_255_255/0.06))] shadow-[0_6px_18px_rgb(0_0_0/0.35)]">
            <Zap className="size-[6.6cqw] fill-[#ffc94d] text-[#ffc94d]" strokeWidth={1.4} />
          </span>
        </div>
        <p className="absolute start-[2.6%] bottom-[4%] m-0 max-w-[94%] rounded-sm bg-black/60 px-1.5 py-0.5 text-[max(9px,2.2cqw)] leading-tight whitespace-nowrap text-white"
          data-testid="sector-art-credit">
          <span className="@max-[260px]:sr-only">{t('photo.label')}: </span>
          {t('photo.creditShort', { creator: photo.creator, license: photo.license })}
        </p>
      </div>
    </div>
  );
}
