import { AnimatePresence, motion, useReducedMotion } from 'motion/react';

import { EDITORIAL_ASSETS, type EditorialId } from '@/content/editorial.generated';
import { cn } from '@/lib/utils';

const srcSet = (id: EditorialId, format: 'avif' | 'webp' | 'jpg') =>
  EDITORIAL_ASSETS[id].widths.map((w) => `/images/editorial/${id}-${w}.${format} ${w}w`).join(', ');

/**
 * A responsive editorial illustration: AVIF, then WebP, then JPEG, at widths no larger
 * than the master (tools/build_editorial_images.py). `sizes` lets the browser fetch a
 * small file on phones; the master itself is never served. Explicit width and height
 * reserve the space, so nothing shifts while it loads.
 */
export function EditorialImage({ id, alt, sizes, eager = false, className }: {
  id: EditorialId;
  alt: string;
  sizes: string;
  eager?: boolean;
  className?: string;
}) {
  const asset = EDITORIAL_ASSETS[id];
  const fallback = asset.widths[Math.min(1, asset.widths.length - 1)] ?? asset.width;
  return (
    <picture>
      <source type="image/avif" srcSet={srcSet(id, 'avif')} sizes={sizes} />
      <source type="image/webp" srcSet={srcSet(id, 'webp')} sizes={sizes} />
      <img
        src={`/images/editorial/${id}-${fallback}.jpg`}
        srcSet={srcSet(id, 'jpg')}
        sizes={sizes}
        width={asset.width}
        height={asset.height}
        alt={alt}
        loading={eager ? 'eager' : 'lazy'}
        fetchPriority={eager ? 'high' : undefined}
        decoding="async"
        className={cn('h-auto w-full', className)}
        data-testid="editorial-image"
        data-asset={id}
      />
    </picture>
  );
}

/**
 * Crossfades between illustrations when `id` changes (for example Electricity to Water).
 * Both images share one grid cell during the fade, so the layout never jumps; with
 * reduced motion the change is immediate.
 */
export function CrossfadeImage(props: Parameters<typeof EditorialImage>[0]) {
  const reduce = useReducedMotion();
  return (
    <div className="grid [&>*]:col-start-1 [&>*]:row-start-1">
      <AnimatePresence initial={false}>
        <motion.div
          key={props.id}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: reduce ? 0 : 0.45, ease: [0.2, 0, 0, 1] }}
        >
          <EditorialImage {...props} />
        </motion.div>
      </AnimatePresence>
    </div>
  );
}
