import type { DataDrivenPropertyValueSpecification, GeoJSONSource, Map as MapLibreMap, MapLayerMouseEvent, StyleSpecification } from 'maplibre-gl';
import { MapPinOff } from 'lucide-react';
import { useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { MAP_STYLE_URL } from './Basemap';
import { resolveTheme, useThemePreference } from '@/lib/theme';
import { Segmented } from '@/components/ui/segmented';
import { formatDecimal } from '@/lib/format';
import { useAppLanguage } from '@/lib/useAppLanguage';

/**
 * Governorates and wilayats of Oman as a choropleth. Boundaries come from OpenStreetMap (ODbL),
 * matched to the area registry by scripts/build_boundaries.py, which also writes the match report
 * (public/geo/boundaries-report.json). Areas without a value are drawn as "No data", never
 * coloured as zero. The provider's basemap is used when it loads; without it the boundaries are
 * drawn on a plain background so the shading still works offline. The table on the page remains
 * the accessible, complete view.
 *
 * Relief: a hillshade from the open Terrain Tiles (Mapzen; SRTM on land, ETOPO1 under the sea)
 * shades mountains such as Al Hajar and Dhofar and the sea floor off the coast, over the shading,
 * whenever the basemap is in use. The basemap follows the theme (OpenFreeMap Positron or Dark)
 * unless VITE_MAP_STYLE_URL names another style.
 */

export type MapLevel = 'governorate' | 'wilayat';
export interface Shade { value: number | null; detail?: string }

const FILES: Record<MapLevel, string> = {
  governorate: '/geo/oman-governorates.geojson',
  wilayat: '/geo/oman-wilayats.geojson',
};
const BOUNDS: [[number, number], [number, number]] = [[51.8, 16.6], [59.9, 26.5]];
// A warm sequential ramp (light peach to burnt umber), readable in both themes; "No data" is a
// separate neutral grey and never part of the ramp.
const RAMP = ['#f6e3d3', '#efc3a1', '#e19a6d', '#c06f43', '#8a4523'];
const NO_DATA = '#bdbcb8';
const CUSTOM_STYLE = import.meta.env.VITE_MAP_STYLE_URL;
const THEMED_STYLE = { light: 'https://tiles.openfreemap.org/styles/positron', dark: 'https://tiles.openfreemap.org/styles/dark' } as const;
/** The basemap for the theme: a configured style in both themes, or OpenFreeMap's matching one. */
function styleFor(theme: 'light' | 'dark'): string | null {
  if (!MAP_STYLE_URL) return null;
  return CUSTOM_STYLE ? MAP_STYLE_URL : THEMED_STYLE[theme];
}
function fallback(theme: 'light' | 'dark'): StyleSpecification {
  return {
    version: 8,
    sources: {},
    layers: [{ id: 'background', type: 'background', paint: { 'background-color': theme === 'dark' ? '#191d20' : '#efe9e1' } }],
  };
}
const SOURCE = 'osrip-areas';
const TERRAIN = 'osrip-terrain';
const TERRAIN_TILES = 'https://elevation-tiles-prod.s3.amazonaws.com/terrarium/{z}/{x}/{y}.png';
const TERRAIN_CREDIT = '<a href="https://github.com/tilezen/joerd/blob/master/docs/attribution.md">Terrain Tiles: Mapzen, SRTM, ETOPO1 and others</a>';

function breaks(values: number[]): number[] {
  const sorted = [...new Set(values)].sort((a, b) => a - b);
  if (sorted.length <= RAMP.length) return sorted;
  return RAMP.map((_, i) => sorted[Math.floor(((i + 1) * (sorted.length - 1)) / RAMP.length)] ?? 0).slice(0, -1);
}

function classOf(value: number, cuts: number[]): number {
  const i = cuts.findIndex((c) => value <= c);
  return i === -1 ? RAMP.length - 1 : Math.min(i, RAMP.length - 1);
}

export function OmanMap({ label, level, onLevelChange, shades, names, legendTitle, selected, onSelect, levels = ['governorate', 'wilayat'] }: {
  label: string;
  level: MapLevel;
  onLevelChange: (level: MapLevel) => void;
  shades: Readonly<Record<string, Shade>>;
  names: Readonly<Record<string, string>>;
  legendTitle: string;
  selected: string | null;
  onSelect: (code: string) => void;
  levels?: readonly MapLevel[];
}) {
  const { t } = useTranslation();
  const language = useAppLanguage();
  const container = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const [state, setState] = useState<'loading' | 'ready' | 'unavailable'>('loading');
  const [basemap, setBasemap] = useState(Boolean(MAP_STYLE_URL));
  const [preference] = useThemePreference();
  const theme = resolveTheme(preference);
  const themeRef = useRef(theme);
  const [hover, setHover] = useState<{ code: string; x: number; y: number } | null>(null);
  const listening = useRef(false);
  // Redraws the boundary layers; called again after every style load (provider or fallback).
  const drawRef = useRef<(() => void) | null>(null);
  const onSelectRef = useRef(onSelect);
  useEffect(() => {
    onSelectRef.current = onSelect;
  }, [onSelect]);

  const values = useMemo(() => Object.values(shades).map((s) => s.value).filter((v): v is number => v !== null), [shades]);
  const cuts = useMemo(() => breaks(values), [values]);
  const colour = useMemo((): DataDrivenPropertyValueSpecification<string> => {
    const pairs: string[] = [];
    for (const [code, s] of Object.entries(shades)) {
      if (s.value !== null) pairs.push(code, RAMP[classOf(s.value, cuts)] ?? NO_DATA);
    }
    return pairs.length
      ? (['match', ['get', 'code'], ...pairs, NO_DATA] as unknown as DataDrivenPropertyValueSpecification<string>)
      : NO_DATA;
  }, [shades, cuts]);

  // Create the map once; fall back to a plain background when the provider's style fails.
  useEffect(() => {
    if (!container.current) return undefined;
    let cancelled = false;
    import('./maplibre')
      .then(({ maplibregl, ensureRtlTextPlugin }) => {
        if (cancelled || !container.current) return;
        ensureRtlTextPlugin();
        const map = new maplibregl.Map({
          container: container.current,
          style: styleFor(themeRef.current) ?? fallback(themeRef.current),
          bounds: BOUNDS,
          fitBoundsOptions: { padding: 16 },
          attributionControl: { compact: false, customAttribution: '© OpenStreetMap contributors (boundaries, ODbL)' },
          cooperativeGestures: true,
          dragRotate: false,
          touchPitch: false,
          pitchWithRotate: false,
        });
        mapRef.current = map;
        map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right');
        let styled = false;
        map.on('style.load', () => {
          styled = true;
          if (!cancelled) setState('ready');
          drawRef.current?.();
        });
        map.on('error', () => {
          if (cancelled || styled) return;
          setBasemap(false);
          map.setStyle(fallback(themeRef.current), { diff: false }); // a full replacement: the first style never loaded
        });
      })
      .catch(() => {
        if (!cancelled) setState('unavailable');
      });
    return () => {
      cancelled = true;
      mapRef.current?.remove();
      mapRef.current = null;
    };
  }, []);

  // The basemap follows the theme (layers are redrawn on the new style's load).
  useEffect(() => {
    if (themeRef.current === theme) return;
    themeRef.current = theme;
    const map = mapRef.current;
    if (!map || state !== 'ready') return;
    const next = basemap ? styleFor(theme) : null;
    map.setStyle(next ?? fallback(theme), { diff: false });
  }, [theme, state, basemap]);

  // (Re)draw the boundary layers for the level, after every style load.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || state !== 'ready') return undefined;
    const draw = () => {
      const data = FILES[level];
      const source = map.getSource<GeoJSONSource>(SOURCE);
      if (source) void source.setData(data);
      else map.addSource(SOURCE, { type: 'geojson', data, promoteId: 'code' });
      // Below the provider's water so the sea covers boundaries drawn out to the territorial limit.
      const layers = map.getStyle().layers;
      const before = layers.find((l) => l.id.startsWith('water'))?.id ?? layers.find((l) => l.type === 'symbol')?.id;
      if (!map.getLayer('osrip-fill')) {
        map.addLayer({ id: 'osrip-fill', type: 'fill', source: SOURCE, paint: { 'fill-color': NO_DATA, 'fill-opacity': 0.82 } }, before);
        // Relief over land and sea, under the labels, only with the provider's basemap (online).
        if (basemap && !map.getSource(TERRAIN)) {
          map.addSource(TERRAIN, { type: 'raster-dem', tiles: [TERRAIN_TILES], tileSize: 256, encoding: 'terrarium', maxzoom: 12, attribution: TERRAIN_CREDIT });
          const label = layers.find((l) => l.type === 'symbol')?.id;
          map.addLayer({
            id: 'osrip-hillshade', type: 'hillshade', source: TERRAIN,
            paint: {
              'hillshade-exaggeration': 0.45,
              'hillshade-shadow-color': themeRef.current === 'dark' ? 'rgba(0,0,0,0.55)' : 'rgba(70,45,25,0.42)',
              'hillshade-highlight-color': themeRef.current === 'dark' ? 'rgba(255,240,225,0.10)' : 'rgba(255,255,255,0.30)',
              'hillshade-accent-color': 'rgba(70,45,25,0.25)',
            },
          }, label);
        }
        const dark = themeRef.current === 'dark';
        map.addLayer({ id: 'osrip-line', type: 'line', source: SOURCE, paint: { 'line-color': dark ? '#d9cfc4' : '#5d4636', 'line-width': 0.8, 'line-opacity': 0.8 } });
        map.addLayer({ id: 'osrip-selected', type: 'line', source: SOURCE, filter: ['==', ['get', 'code'], ''], paint: { 'line-color': dark ? '#f4a873' : '#8a4523', 'line-width': 3 } });
      }
      if (!listening.current) {
        // Attached once the layer exists; they stay with the map across style changes.
        listening.current = true;
        map.on('mousemove', 'osrip-fill', (e: MapLayerMouseEvent) => {
          const code = e.features?.[0]?.properties?.code as string | undefined;
          map.getCanvas().style.cursor = code ? 'pointer' : '';
          setHover(code ? { code, x: e.point.x, y: e.point.y } : null);
        });
        map.on('mouseleave', 'osrip-fill', () => {
          map.getCanvas().style.cursor = '';
          setHover(null);
        });
        map.on('click', 'osrip-fill', (e: MapLayerMouseEvent) => {
          const code = e.features?.[0]?.properties?.code as string | undefined;
          if (code) onSelectRef.current(code);
        });
      }
      map.setPaintProperty('osrip-fill', 'fill-color', colour);
      map.setFilter('osrip-selected', ['==', ['get', 'code'], selected ?? '']);
    };
    drawRef.current = draw;
    draw();
    return () => {
      drawRef.current = null;
    };
  }, [state, level, colour, selected, basemap]);

  if (state === 'unavailable') {
    return (
      <div role="status" data-testid="oman-map-unavailable" className="flex min-h-48 items-start gap-3 rounded-lg border border-dashed border-border-strong/50 bg-card/60 p-6">
        <MapPinOff aria-hidden="true" className="size-5 shrink-0 text-muted-foreground" />
        <p className="max-w-prose text-sm text-muted-foreground">{t('omanMap.unavailable')}</p>
      </div>
    );
  }

  // One entry per class: exact values when there are few, otherwise ranges up to the maximum.
  const exact = new Set(values).size <= RAMP.length;
  const max = values.length ? Math.max(...values) : 0;
  const last = cuts[cuts.length - 1];
  const tops = !exact && last !== undefined && max > last ? [...cuts, max] : cuts;
  const legend = tops.map((high, i) => ({
    low: exact ? high : i === 0 ? Math.min(...values) : (tops[i - 1] ?? high),
    high,
    colour: RAMP[classOf(high, cuts)] ?? NO_DATA,
  }));
  const shown = hover ? shades[hover.code] : undefined;
  const n = (v: number) => formatDecimal(String(v), language, 2) ?? String(v);

  return (
    <div className="flex flex-col gap-3" data-testid="oman-map" data-level={level}>
      <div className="flex flex-wrap items-center justify-between gap-3">
        {levels.length > 1 ? (
          <Segmented label={t('omanMap.level')} value={level} onChange={onLevelChange} testId="map-level" className="w-80 max-w-full"
            options={levels.map((l) => ({ value: l, label: t(`omanMap.levels.${l}`) }))} />
        ) : <span />}
        <p className="text-xs text-muted-foreground">{basemap ? t('omanMap.withBasemap') : t('omanMap.withoutBasemap')}</p>
      </div>
      <div className="relative overflow-hidden rounded-lg border border-border bg-muted">
        <div ref={container} role="region" aria-label={label} data-testid="oman-map-canvas" data-state={state} className="h-96 w-full lg:h-[28rem]" />
        {state === 'loading' ? <p role="status" className="absolute inset-0 flex items-center justify-center text-sm text-muted-foreground">{t('omanMap.loading')}</p> : null}
        {hover ? (
          <div className="pointer-events-none absolute z-10 max-w-64 rounded-md border border-border bg-card px-3 py-2 text-sm shadow-card"
            style={{ left: Math.min(hover.x + 12, 9999), top: hover.y + 12 }} data-testid="map-tooltip">
            <p className="font-semibold">{names[hover.code] ?? hover.code}</p>
            <p className="text-muted-foreground">{shown && shown.value !== null ? (shown.detail ?? n(shown.value)) : (shown?.detail ?? t('omanMap.noData'))}</p>
          </div>
        ) : null}
      </div>
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-xs" data-testid="map-legend">
        <span className="font-medium">{legendTitle}</span>
        {legend.map(({ low, high, colour: swatch }) => (
          <span key={`${low}-${high}`} className="inline-flex items-center gap-1.5">
            <span aria-hidden="true" className="size-3 rounded-sm border border-border-strong/40" style={{ backgroundColor: swatch }} />
            <span className="tabular-nums" dir="ltr">{low === high ? n(high) : `${n(low)} – ${n(high)}`}</span>
          </span>
        ))}
        <span className="inline-flex items-center gap-1.5">
          <span aria-hidden="true" className="size-3 rounded-sm border border-dashed border-border-strong" style={{ backgroundColor: NO_DATA }} />
          {t('omanMap.noData')}
        </span>
      </div>
    </div>
  );
}
