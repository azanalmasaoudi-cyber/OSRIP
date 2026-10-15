import { useCallback, type PointerEvent } from 'react';

const still = () =>
  typeof window === 'undefined' ||
  window.matchMedia('(prefers-reduced-motion: reduce)').matches ||
  window.matchMedia('(pointer: coarse)').matches;

/**
 * Gentle pointer-following depth for a card or scene (see .tilt / .scene in index.css).
 * Writes two CSS variables on the element; no React state, so nothing re-renders.
 * Mouse and pen only: touch screens and reduced-motion settings keep the flat
 * 2D layout, and keyboard users get the same focus lift through :focus-within.
 */
export function useTilt(maxDegrees = 4) {
  const onPointerMove = useCallback((event: PointerEvent<HTMLElement>) => {
    if (event.pointerType === 'touch' || still()) return;
    const el = event.currentTarget;
    const box = el.getBoundingClientRect();
    const x = (event.clientX - box.left) / box.width - 0.5;
    const y = (event.clientY - box.top) / box.height - 0.5;
    el.style.setProperty('--tilt-x', `${(-y * maxDegrees).toFixed(2)}deg`);
    el.style.setProperty('--tilt-y', `${(x * maxDegrees).toFixed(2)}deg`);
  }, [maxDegrees]);
  const onPointerLeave = useCallback((event: PointerEvent<HTMLElement>) => {
    event.currentTarget.style.removeProperty('--tilt-x');
    event.currentTarget.style.removeProperty('--tilt-y');
  }, []);
  return { onPointerMove, onPointerLeave };
}
