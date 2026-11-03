import type {
  ControlPosition, DataDrivenPropertyValueSpecification, GeoJSONSource, IControl, Map as MapLibreMap, MapLayerMouseEvent, StyleSpecification,
} from 'maplibre-gl';
import { Box, Layers, LocateFixed, MapPinOff, Mountain, Satellite } from 'lucide-react';
import { useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';

import {
  MAX_BOUNDS, OMAN_BOUNDS, isOtherProvider, isProviderFailure, maptilerConfigured, plainStyle, providerChain,
  type MapTheme, type MapView, type Provider,
} from './mapProviders';
import { Segmented } from '@/components/ui/segmented';
import { formatDecimal } from '@/lib/format';
import { resolveTheme, useThemePreference } from '@/lib/theme';
import { useAppLanguage } from '@/lib/useAppLanguage';
import { cn } from '@/lib/utils';

/**
 * The Oman geographic intelligence map: governorates and wilayats of the Sultanate (Musandam
 * included) as a choropleth, with Arabic and English names, on a MapTiler basemap when a key is
 * configured (Topographic, Satellite, Terrain; optional 3D terrain) or on OpenFreeMap with open
 * terrain otherwise (components/geography/mapProviders.ts).
 *
 * * Scope: the camera is held to Oman and everything outside the national outline is dimmed. The
 *   outline is dissolved from the governorates' OpenStreetMap ways (scripts/build_boundaries.py),
 *   not a rectangle.
 * * Values: areas without a published value are "No data", never coloured as zero.
 * * Cost: the map is created only when it scrolls into view, tiles are never re-requested when
 *   they expire, 3D is off until asked for, and a failing provider hands over to the next.
 * The table on the page remains the accessible, complete view.
 */

export type MapLevel = 'governorate' | 'wilayat';
export interface Shade { value: number | null; detail?: string }

const FILES: Record<MapLevel, string> = {
  governorate: '/geo/oman-governorates.geojson',
  wilayat: '/geo/oman-wilayats.geojson',
};
const MASK_FILE = '/geo/oman-mask.geojson';
const NATIONAL_FILE = '/geo/oman-national.geojson';
const LABELS_FILE = '/geo/oman-labels.geojson';
// A warm sequential ramp (light peach to burnt umber), readable in both themes; "No data" is a
// separate neutral grey and never part of the ramp.
const RAMP = ['#f6e3d3', '#efc3a1', '#e19a6d', '#c06f43', '#8a4523'];
const NO_DATA = '#bdbcb8';
const SOURCE = 'osrip-areas';
// Elevation: one source for the relief shading and another for 3D terrain, as MapLibre advises
// (sharing one lowers the quality of both). The terrain source is added only while 3D is on.
const DEM = 'osrip-dem';
const TERRAIN = 'osrip-terrain';
const VIEW_KEY = 'osrip.map.view';
const VIEWS: readonly MapView[] = ['topographic', 'satellite', 'terrain'];

function breaks(values: number[]): number[] {
  const sorted = [...new Set(values)].sort((a, b) => a - b);
  if (sorted.length <= RAMP.length) return sorted;
  return RAMP.map((_, i) => sorted[Math.floor(((i + 1) * (sorted.length - 1)) / RAMP.length)] ?? 0).slice(0, -1);
}

function classOf(value: number, cuts: number[]): number {
  const i = cuts.findIndex((c) => value <= c);
  return i === -1 ? RAMP.length - 1 : Math.min(i, RAMP.length - 1);
}

function readView(): MapView {
  try {
    const v = window.localStorage.getItem(VIEW_KEY);
    return VIEWS.find((x) => x === v) ?? 'topographic';
  } catch {
    return 'topographic';
  }
}

const reducedMotion = () => typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;

/**
 * An upright text font from the style itself (its glyph server has it; the first symbol layers
 * are usually italic water names), else any of its fonts, else OpenFreeMap's Noto Sans.
 */
function textFont(map: MapLibreMap): string[] {
  let any: string[] | null = null;
  for (const layer of map.getStyle().layers) {
    if (layer.type !== 'symbol') continue;
    const font: unknown = map.getLayoutProperty(layer.id, 'text-font');
    if (!Array.isArray(font) || !font.length || !font.every((f): f is string => typeof f === 'string')) continue;
    if (font.some((f) => /regular/i.test(f)) && !font.some((f) => /italic/i.test(f))) return font;
    any ??= font;
  }
  return any ?? ['Noto Sans Regular'];
}

type Bbox = [number, number, number, number];

/** Bounding boxes of every area in a FeatureCollection, by code (for zooming to a selection). */
function bboxes(collection: { features: { id?: string; properties?: { code?: string }; geometry: { coordinates: number[][][][] } }[] }): Record<string, Bbox> {
  const out: Record<string, Bbox> = {};
  for (const f of collection.features) {
    const code = f.properties?.code ?? f.id;
    if (!code) continue;
    let box: Bbox = [180, 90, -180, -90];
    for (const poly of f.geometry.coordinates) {
      for (const [x, y] of poly[0] ?? []) {
        if (x === undefined || y === undefined) continue;
        box = [Math.min(box[0], x), Math.min(box[1], y), Math.max(box[2], x), Math.max(box[3], y)];
      }
    }
    out[code] = box;
  }
  return out;
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
  const [preference] = useThemePreference();
  const theme: MapTheme = resolveTheme(preference);
  const container = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const chain = useMemo(() => providerChain(), []);
  const [providerIndex, setProviderIndex] = useState(0);
  const providerRef = useRef<Provider>(chain[0]!);
  const provider = chain[Math.min(providerIndex, chain.length - 1)]!;
  const [fellBack, setFellBack] = useState(false);
  // Without IntersectionObserver (old browsers) the map loads at once.
  const [visible, setVisible] = useState(() => typeof IntersectionObserver === 'undefined');
  const [state, setState] = useState<'idle' | 'loading' | 'ready' | 'unavailable'>('idle');
  const [chosenView, setChosenView] = useState<MapView>(readView);
  const view: MapView = provider.style(chosenView, theme) === null ? 'topographic' : chosenView;
  const [threeD, setThreeD] = useState(false);
  const [hover, setHover] = useState<{ code: string; x: number; y: number } | null>(null);
  const [boxes, setBoxes] = useState<Record<string, Bbox>>({});
  const listening = useRef(false);
  const styleKey = useRef('');
  // True between a style's "style.load" and the next setStyle. map.isStyleLoaded() is no guide:
  // it stays false until every tile has arrived, while sources and layers can be added at once.
  const styleReady = useRef(false);
  // The zoom buttons and the corner they sit in (the end edge, opposite the toolbar).
  const nav = useRef<{ control: IControl; corner: ControlPosition | null } | null>(null);
  // Redraws OSRIP's layers; called again after every style load (theme, view or provider change).
  const drawRef = useRef<(() => void) | null>(null);
  const onSelectRef = useRef(onSelect);
  useEffect(() => {
    onSelectRef.current = onSelect;
  }, [onSelect]);
  useEffect(() => {
    providerRef.current = provider;
  }, [provider]);

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

  // Lazy: nothing is requested until the map is on screen.
  useEffect(() => {
    const el = container.current;
    if (!el || visible) return undefined;
    const observer = new IntersectionObserver((entries) => {
      if (entries.some((e) => e.isIntersecting)) setVisible(true);
    }, { rootMargin: '200px' });
    observer.observe(el);
    return () => observer.disconnect();
  }, [visible]);

  // Area boxes for zooming to a selection (the same files the map draws).
  useEffect(() => {
    if (!visible) return;
    let cancelled = false;
    void Promise.all([FILES.governorate, FILES.wilayat].map((f) => fetch(f).then((r) => r.json() as Promise<Parameters<typeof bboxes>[0]>)))
      .then((collections) => {
        if (!cancelled) setBoxes(Object.assign({}, ...collections.map(bboxes)) as Record<string, Bbox>);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [visible]);

  const styleFor = (p: Provider, v: MapView, th: MapTheme): string | StyleSpecification => p.style(v, th) ?? plainStyle(th);

  // Create the map once it is visible.
  useEffect(() => {
    if (!visible || !container.current) return undefined;
    let cancelled = false;
    setState('loading');
    import('./maplibre')
      .then(({ maplibregl, ensureRtlTextPlugin }) => {
        if (cancelled || !container.current) return;
        ensureRtlTextPlugin();
        const first = providerRef.current;
        styleKey.current = `${first.id}:${view}:${theme}`;
        const map = new maplibregl.Map({
          container: container.current,
          style: styleFor(first, view, theme),
          bounds: OMAN_BOUNDS,
          maxBounds: MAX_BOUNDS,
          fitBoundsOptions: { padding: 16 },
          renderWorldCopies: false,
          refreshExpiredTiles: false, // no repeat (billable) requests for tiles already shown
          maxPitch: 70,
          // Compact (an "i" button) on narrow maps, in full otherwise.
          attributionControl: { customAttribution: '© OpenStreetMap contributors (boundaries, ODbL)' },
          cooperativeGestures: true,
          dragRotate: false,
          touchPitch: false,
          pitchWithRotate: false,
        });
        mapRef.current = map;
        nav.current = { control: new maplibregl.NavigationControl({ showCompass: false }), corner: null };
        map.addControl(new maplibregl.ScaleControl({ unit: 'metric' }), 'bottom-right');
        let styled = false;
        map.on('style.load', () => {
          styled = true;
          styleReady.current = true;
          if (!cancelled) setState('ready');
          drawRef.current?.();
        });
        // A provider that refuses (bad key or origin, quota, outage) hands over to the next one.
        map.on('error', (event) => {
          if (cancelled) return;
          const err = event.error as (Error & { url?: string; status?: number }) | undefined;
          const current = providerRef.current;
          // Before the first style loads any error means the provider cannot be used; afterwards
          // only the current provider's own refusals count (a missing tile does not). Late errors
          // from a provider already left behind are ignored, so one failure moves on one step.
          if (current.id === 'plain' || isOtherProvider(current.id, err?.url)) return;
          if (styled && !isProviderFailure(current.id, err?.url, err?.status)) return;
          setProviderIndex((i) => (chain[i]?.id === current.id ? Math.min(i + 1, chain.length - 1) : i));
          setFellBack(true);
        });
      })
      .catch(() => {
        // WebGL unavailable or the map library failed to load.
        if (!cancelled) setState('unavailable');
      });
    return () => {
      cancelled = true;
      mapRef.current?.remove();
      mapRef.current = null;
      nav.current = null;
      listening.current = false;
      styleReady.current = false;
    };
    // The map is created once; style changes go through setStyle below.
  }, [visible]); // eslint-disable-line react-hooks/exhaustive-deps

  // Zoom buttons at the end edge: right in English, left in Arabic (the toolbar takes the start).
  useEffect(() => {
    const map = mapRef.current;
    const zoom = nav.current;
    if (!map || !zoom || state !== 'ready') return;
    const corner: ControlPosition = language === 'ar' ? 'top-left' : 'top-right';
    if (zoom.corner === corner) return;
    if (zoom.corner) map.removeControl(zoom.control);
    map.addControl(zoom.control, corner);
    zoom.corner = corner;
  }, [language, state]);

  // Theme, view or provider changed: load the matching style (layers are redrawn on load).
  useEffect(() => {
    const map = mapRef.current;
    if (!map || state === 'idle' || state === 'unavailable') return;
    const key = `${provider.id}:${view}:${theme}`;
    if (key === styleKey.current) return;
    styleKey.current = key;
    styleReady.current = false;
    map.setStyle(styleFor(provider, view, theme), { diff: false });
  }, [provider, view, theme, state]);

  // OSRIP's layers, (re)drawn after each style load and whenever their inputs change.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || state !== 'ready') return undefined;
    const draw = () => {
      if (!styleReady.current) return;
      const dark = theme === 'dark';
      const layers = map.getStyle().layers;
      const firstSymbol = layers.find((l) => l.type === 'symbol')?.id;
      const water = layers.find((l) => l.id.startsWith('water'))?.id ?? firstSymbol;
      const dem = provider.dem();
      const source = map.getSource<GeoJSONSource>(SOURCE);
      if (source) void source.setData(FILES[level]);
      else map.addSource(SOURCE, { type: 'geojson', data: FILES[level], promoteId: 'code' });
      if (!map.getLayer('osrip-fill')) {
        // Under the provider's water, so the sea covers boundaries drawn to the territorial limit.
        map.addLayer({ id: 'osrip-fill', type: 'fill', source: SOURCE, paint: { 'fill-color': NO_DATA, 'fill-opacity': view === 'satellite' ? 0.55 : 0.82 } }, water);
        // Relief over the shading where the basemap has none of its own.
        if (dem && !provider.styleHasRelief(view)) {
          if (!map.getSource(DEM)) map.addSource(DEM, dem);
          map.addLayer({
            id: 'osrip-hillshade', type: 'hillshade', source: DEM,
            paint: {
              'hillshade-exaggeration': 0.45,
              'hillshade-shadow-color': dark ? 'rgba(0,0,0,0.55)' : 'rgba(70,45,25,0.42)',
              'hillshade-highlight-color': dark ? 'rgba(255,240,225,0.10)' : 'rgba(255,255,255,0.30)',
              'hillshade-accent-color': 'rgba(70,45,25,0.25)',
            },
          }, firstSymbol);
        }
        // Outside Oman: dimmed, labels included.
        map.addSource('osrip-mask', { type: 'geojson', data: MASK_FILE });
        map.addLayer({ id: 'osrip-mask', type: 'fill', source: 'osrip-mask', paint: { 'fill-color': dark ? '#101315' : '#f7f3ee', 'fill-opacity': 0.62 } });
        map.addSource('osrip-national', { type: 'geojson', data: NATIONAL_FILE });
        map.addLayer({ id: 'osrip-national', type: 'line', source: 'osrip-national', paint: { 'line-color': dark ? '#f4a873' : '#8a4523', 'line-width': 1.6 } });
        map.addLayer({ id: 'osrip-line', type: 'line', source: SOURCE, paint: { 'line-color': dark ? '#d9cfc4' : '#5d4636', 'line-width': 0.8, 'line-opacity': 0.8 } });
        map.addLayer({ id: 'osrip-hover', type: 'line', source: SOURCE, filter: ['==', ['get', 'code'], ''], paint: { 'line-color': dark ? '#f6f3ef' : '#292623', 'line-width': 2 } });
        map.addLayer({ id: 'osrip-selected', type: 'line', source: SOURCE, filter: ['==', ['get', 'code'], ''], paint: { 'line-color': dark ? '#f4a873' : '#8a4523', 'line-width': 3 } });
        map.addSource('osrip-labels', { type: 'geojson', data: LABELS_FILE });
        map.addLayer({
          id: 'osrip-labels', type: 'symbol', source: 'osrip-labels',
          layout: { 'text-font': textFont(map), 'text-size': 12, 'text-max-width': 8, 'text-padding': 4 },
          paint: { 'text-color': dark ? '#f6f3ef' : '#292623', 'text-halo-color': dark ? 'rgba(16,19,21,0.85)' : 'rgba(247,243,238,0.9)', 'text-halo-width': 1.4 },
        });
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
      map.setFilter('osrip-labels', ['==', ['get', 'level'], level]);
      map.setLayoutProperty('osrip-labels', 'text-field', ['get', language === 'ar' ? 'name_ar' : 'name_en']);
      map.setFilter('osrip-selected', ['==', ['get', 'code'], selected ?? '']);
      // 3D only on request: the terrain source adds tile requests and GPU work.
      if (threeD && dem) {
        if (!map.getSource(TERRAIN)) map.addSource(TERRAIN, dem);
        map.setTerrain({ source: TERRAIN, exaggeration: 1.4 });
        map.dragRotate.enable();
        map.touchPitch.enable();
      } else {
        map.setTerrain(null);
        map.dragRotate.disable();
        map.touchPitch.disable();
      }
    };
    drawRef.current = draw;
    draw();
    return () => {
      drawRef.current = null;
    };
  }, [state, level, colour, selected, language, threeD, provider, view, theme]);

  // The hovered area's outline (cheap: a filter change only).
  useEffect(() => {
    const map = mapRef.current;
    if (!map || state !== 'ready' || !map.getLayer('osrip-hover')) return;
    map.setFilter('osrip-hover', ['==', ['get', 'code'], hover?.code ?? '']);
  }, [hover, state]);

  // Tilt in and out with 3D; fly to a selected area.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || state !== 'ready') return;
    map.easeTo({ pitch: threeD ? 55 : 0, bearing: threeD ? map.getBearing() : 0, duration: reducedMotion() ? 0 : 700 });
  }, [threeD, state]);
  useEffect(() => {
    const map = mapRef.current;
    const box = selected ? boxes[selected] : undefined;
    if (!map || state !== 'ready' || !box) return;
    map.fitBounds([[box[0], box[1]], [box[2], box[3]]], { padding: 48, maxZoom: 9, duration: reducedMotion() ? 0 : 800 });
  }, [selected, boxes, state]);

  const chooseView = (next: MapView) => {
    setChosenView(next);
    try {
      window.localStorage.setItem(VIEW_KEY, next);
    } catch {
      // Storage blocked: the choice lasts for this page only.
    }
  };
  const resetView = () => mapRef.current?.fitBounds(OMAN_BOUNDS, { padding: 16, pitch: threeD ? 55 : 0, bearing: 0, duration: reducedMotion() ? 0 : 700 });

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
  const satelliteAvailable = provider.style('satellite', theme) !== null;
  const viewIcon = { topographic: Layers, satellite: Satellite, terrain: Mountain } as const;
  const hasDem = provider.dem() !== null;

  return (
    <div className="flex flex-col gap-3" data-testid="oman-map" data-level={level} data-provider={provider.id} data-view={view} data-3d={threeD || undefined}>
      <div className="flex flex-wrap items-center justify-between gap-3">
        {levels.length > 1 ? (
          <Segmented label={t('omanMap.level')} value={level} onChange={onLevelChange} testId="map-level" className="w-80 max-w-full"
            options={levels.map((l) => ({ value: l, label: t(`omanMap.levels.${l}`) }))} />
        ) : <span />}
        <p className="text-xs text-muted-foreground" data-testid="map-provider">{t(`omanMap.provider.${provider.id}`)}</p>
      </div>
      {fellBack ? <p role="status" className="text-xs text-muted-foreground" data-testid="map-fallback">{t('omanMap.fallback')}</p> : null}
      <div className="relative overflow-hidden rounded-xl border border-border bg-muted shadow-card">
        <div ref={container} role="region" aria-label={label} data-testid="oman-map-canvas" data-state={state} className="h-[26rem] w-full lg:h-[32rem]" />
        {state === 'ready' ? (
          <div className="glass-card glass-strong absolute top-3 start-3 z-10 flex max-w-[calc(100%-4.5rem)] flex-wrap items-center gap-1 rounded-xl border p-1 shadow-raised" data-testid="map-toolbar">
            <div role="radiogroup" aria-label={t('omanMap.view')} className="flex">
              {VIEWS.map((v) => {
                const Icon = viewIcon[v];
                const disabled = v === 'satellite' && !satelliteAvailable;
                return (
                  <button key={v} type="button" role="radio" aria-checked={view === v} disabled={disabled}
                    title={disabled ? t('omanMap.satelliteNeedsKey') : undefined}
                    onClick={() => chooseView(v)} data-testid={`map-view-${v}`}
                    className={cn('inline-flex min-h-9 items-center gap-1.5 rounded-lg px-2.5 text-sm transition-colors disabled:cursor-not-allowed disabled:opacity-45',
                      view === v ? 'bg-primary-soft font-semibold text-foreground' : 'text-muted-foreground hover:bg-muted hover:text-foreground')}>
                    <Icon aria-hidden="true" className="size-4" /><span className="max-sm:sr-only">{t(`omanMap.views.${v}`)}</span>
                  </button>
                );
              })}
            </div>
            <span aria-hidden="true" className="mx-0.5 h-6 w-px bg-border" />
            <button type="button" aria-pressed={threeD} disabled={!hasDem} onClick={() => setThreeD((v) => !v)} data-testid="map-3d"
              title={hasDem ? undefined : t('omanMap.noTerrain')}
              className={cn('inline-flex min-h-9 items-center gap-1.5 rounded-lg px-2.5 text-sm transition-colors disabled:opacity-45',
                threeD ? 'bg-primary-soft font-semibold text-foreground' : 'text-muted-foreground hover:bg-muted hover:text-foreground')}>
              <Box aria-hidden="true" className="size-4" />3D
            </button>
            <button type="button" onClick={resetView} data-testid="map-reset" aria-label={t('omanMap.reset')} title={t('omanMap.reset')}
              className="inline-flex size-9 items-center justify-center rounded-lg text-muted-foreground hover:bg-muted hover:text-foreground">
              <LocateFixed aria-hidden="true" className="size-4" />
            </button>
          </div>
        ) : null}
        {state === 'ready' && provider.id === 'maptiler' ? (
          // MapTiler's terms ask for its logo on the map (MapLibre, unlike MapTiler's SDK, does not add it).
          <a href="https://www.maptiler.com" target="_blank" rel="noreferrer" className="absolute bottom-2 start-2 z-10" data-testid="maptiler-logo">
            <img src="https://api.maptiler.com/resources/logo.svg" alt="MapTiler" className="h-5 w-auto" />
          </a>
        ) : null}
        {state === 'loading' || state === 'idle' ? <p role="status" className="absolute inset-0 flex items-center justify-center text-sm text-muted-foreground">{t('omanMap.loading')}</p> : null}
        {hover ? (
          <div className="glass-card glass-strong pointer-events-none absolute z-10 max-w-64 rounded-lg border px-3 py-2 text-sm shadow-raised"
            style={{ left: Math.min(hover.x + 12, 9999), top: hover.y + 12 }} data-testid="map-tooltip">
            <p className="font-semibold">{names[hover.code] ?? hover.code}</p>
            <p className="text-muted-foreground">{shown && shown.value !== null ? (shown.detail ?? n(shown.value)) : (shown?.detail ?? t('omanMap.noData'))}</p>
          </div>
        ) : null}
      </div>
      <div className="glass-card flex flex-wrap items-center gap-x-4 gap-y-2 rounded-xl border px-4 py-2.5 text-xs" data-testid="map-legend">
        <span className="font-medium">{legendTitle}</span>
        {legend.map(({ low, high, colour: swatch }) => (
          <span key={`${low}-${high}`} className="inline-flex items-center gap-1.5" data-testid="map-legend-class">
            <span aria-hidden="true" className="size-3 rounded-sm border border-border-strong/40" style={{ backgroundColor: swatch }} />
            <span className="tabular-nums" dir="ltr">{low === high ? n(high) : `${n(low)} – ${n(high)}`}</span>
          </span>
        ))}
        <span className="inline-flex items-center gap-1.5">
          <span aria-hidden="true" className="size-3 rounded-sm border border-dashed border-border-strong" style={{ backgroundColor: NO_DATA }} />
          {t('omanMap.noData')}
        </span>
        {maptilerConfigured ? null : <span className="ms-auto text-muted-foreground" data-testid="map-key-note">{t('omanMap.keyNote')}</span>}
      </div>
    </div>
  );
}
