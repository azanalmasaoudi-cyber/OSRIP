import type { SourceSpecification, StyleSpecification } from 'maplibre-gl';

/**
 * Map providers for the Oman map, in order of preference:
 *
 * 1. MapTiler Cloud, when VITE_MAPTILER_KEY is set: Topo, Satellite Hybrid and Landscape (relief)
 *    styles in light and dark, and the Terrain RGB tiles for 3D. The key is a browser key:
 *    every viewer can read it, so it must be restricted to the site's addresses ("Allowed HTTP
 *    origins") in the MapTiler account. Used through MapLibre GL JS, MapTiler counts each tile
 *    request (not sessions); see docs/MAP.md for limits and costs.
 * 2. OpenFreeMap (OpenStreetMap vector tiles, free, no key) with the open Terrain Tiles (Mapzen;
 *    SRTM on land, ETOPO1 under the sea) for relief and 3D. No satellite view.
 * 3. A plain background (no external requests), when VITE_MAP_STYLE_URL is "none" or both
 *    providers fail. The boundaries, shading and labels still draw.
 *
 * Style IDs are MapTiler's published map IDs (as listed by @maptiler/client 3.1.0).
 */

export type MapView = 'topographic' | 'satellite' | 'terrain';
export type MapTheme = 'light' | 'dark';
export type ProviderId = 'maptiler' | 'openfreemap' | 'plain';

const MAPTILER_KEY = (import.meta.env.VITE_MAPTILER_KEY ?? '').trim() || null;
const CUSTOM_STYLE = import.meta.env.VITE_MAP_STYLE_URL;
const OPEN_DISABLED = CUSTOM_STYLE === 'none';

const MAPTILER_STYLES: Record<MapView, Record<MapTheme, string>> = {
  topographic: { light: 'topo-v4', dark: 'topo-v4-dark' },
  satellite: { light: 'hybrid-v4', dark: 'hybrid-v4-dark' },
  terrain: { light: 'landscape-v4', dark: 'landscape-v4-dark' },
};
const OPENFREEMAP: Record<MapTheme, string> = {
  light: 'https://tiles.openfreemap.org/styles/positron',
  dark: 'https://tiles.openfreemap.org/styles/dark',
};
const OPEN_TERRAIN_TILES = 'https://elevation-tiles-prod.s3.amazonaws.com/terrarium/{z}/{x}/{y}.png';
const OPEN_TERRAIN_CREDIT = '<a href="https://github.com/tilezen/joerd/blob/master/docs/attribution.md">Terrain Tiles: Mapzen, SRTM, ETOPO1 and others</a>';

/** The Sultanate of Oman including Musandam, with a margin: the opening view. */
export const OMAN_BOUNDS: [[number, number], [number, number]] = [[51.9, 16.6], [59.9, 26.6]];
/**
 * The camera cannot leave this box. Oman is taller than it is wide, so a wide (about 2:1) map
 * needs roughly 2.5 times its height in longitude to show the whole country; a tighter box
 * would force the map to zoom in past Musandam and Dhofar. Outside the outline is dimmed.
 */
export const MAX_BOUNDS: [[number, number], [number, number]] = [[43.5, 11.5], [68.5, 31.5]];

export interface Provider {
  id: ProviderId;
  /** The style for a view and theme, or null when this provider has no such view. */
  style: (view: MapView, theme: MapTheme) => string | StyleSpecification | null;
  /** The elevation source for relief shading and 3D terrain, or null. */
  dem: () => SourceSpecification | null;
  /** Whether the style already shades relief (no extra hillshade layer needed). */
  styleHasRelief: (view: MapView) => boolean;
}

export const maptilerConfigured = MAPTILER_KEY !== null;

const maptiler: Provider = {
  id: 'maptiler',
  style: (view, theme) => `https://api.maptiler.com/maps/${MAPTILER_STYLES[view][theme]}/style.json?key=${MAPTILER_KEY ?? ''}`,
  dem: () => ({ type: 'raster-dem', url: `https://api.maptiler.com/tiles/terrain-rgb-v2/tiles.json?key=${MAPTILER_KEY ?? ''}` }),
  styleHasRelief: () => true, // Topo, Hybrid and Landscape all shade relief themselves
};

const openfreemap: Provider = {
  id: 'openfreemap',
  style: (view, theme) => (view === 'satellite' ? null : CUSTOM_STYLE && !OPEN_DISABLED ? CUSTOM_STYLE : OPENFREEMAP[theme]),
  dem: () => ({ type: 'raster-dem', tiles: [OPEN_TERRAIN_TILES], tileSize: 256, encoding: 'terrarium', maxzoom: 12, attribution: OPEN_TERRAIN_CREDIT }),
  styleHasRelief: () => false,
};

/** No external requests: a background and OpenFreeMap's glyphs for the area names. */
export function plainStyle(theme: MapTheme): StyleSpecification {
  return {
    version: 8,
    glyphs: OPEN_DISABLED ? undefined : 'https://tiles.openfreemap.org/fonts/{fontstack}/{range}.pbf',
    sources: {},
    layers: [{ id: 'background', type: 'background', paint: { 'background-color': theme === 'dark' ? '#191d20' : '#efe9e1' } }],
  };
}

const plain: Provider = {
  id: 'plain',
  style: (view, theme) => (view === 'satellite' ? null : plainStyle(theme)),
  dem: () => null,
  styleHasRelief: () => false,
};

/** The providers to try, best first. */
export function providerChain(): Provider[] {
  return [...(MAPTILER_KEY ? [maptiler] : []), ...(OPEN_DISABLED ? [] : [openfreemap]), plain];
}

/** True when a failed request belongs to the provider (so the next one should take over). */
export function isProviderFailure(provider: ProviderId, url: string | undefined, status: number | undefined): boolean {
  if (!url) return false;
  if (provider === 'maptiler') return url.includes('api.maptiler.com') && (status === undefined || [401, 403, 429].includes(status) || status >= 500);
  if (provider === 'openfreemap') return url.includes('openfreemap.org') && url.includes('/styles/');
  return false;
}

/** True when a failed request came from another provider (a late error after a hand-over). */
export function isOtherProvider(provider: ProviderId, url: string | undefined): boolean {
  if (!url) return false;
  if (url.includes('api.maptiler.com')) return provider !== 'maptiler';
  if (url.includes('openfreemap.org/styles/') || (CUSTOM_STYLE && url === CUSTOM_STYLE)) return provider !== 'openfreemap';
  return false;
}
