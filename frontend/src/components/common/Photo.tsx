import { useTranslation } from 'react-i18next';

import type { PhotoCredit } from '@/content/photos';
import { useAppLanguage } from '@/lib/useAppLanguage';
import { cn } from '@/lib/utils';

interface PhotoProps {
  photo: PhotoCredit;
  className?: string;
  imgClassName?: string;
  /** `overlay` sets the credit over the image (hero); `below` under it. */
  credit?: 'overlay' | 'below';
  priority?: boolean;
}

/** A credited photograph: location, creator and licence are always visible. */
export function Photo({ photo, className, imgClassName, credit = 'below', priority = false }: PhotoProps) {
  const language = useAppLanguage();
  return (
    <figure className={cn('relative m-0', className)} data-testid="photo">
      <img
        src={photo.src}
        width={photo.width}
        height={photo.height}
        alt={photo.alt[language]}
        loading={priority ? 'eager' : 'lazy'}
        decoding="async"
        className={cn('block w-full object-cover', imgClassName)}
      />
      <PhotoCaption
        photo={photo}
        className={
          credit === 'overlay'
            ? 'on-nav absolute end-0 bottom-0 max-w-full rounded-ss-md bg-black/65 px-3 py-1.5 text-white [&_a]:text-white'
            : 'pt-2 text-muted-foreground'
        }
      />
    </figure>
  );
}

/** Credit line. `standalone` renders a <p> for images that are not inside a <figure>. */
export function PhotoCaption({ photo, className, standalone = false }: { photo: PhotoCredit; className?: string; standalone?: boolean }) {
  const { t } = useTranslation();
  const language = useAppLanguage();
  const Tag = standalone ? 'p' : 'figcaption';
  return (
    <Tag className={cn('text-xs leading-relaxed', className)} data-testid="photo-credit">
      <span className="font-medium">{photo.location[language]}</span>
      <span aria-hidden="true"> · </span>
      <a href={photo.sourceUrl} target="_blank" rel="noreferrer" className="underline underline-offset-2 hover:no-underline">
        {t('photo.credit', { creator: photo.creator, license: photo.license })}
      </a>
    </Tag>
  );
}
