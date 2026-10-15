import type { ExpressionSpecification, Map as MapLibreMap } from 'maplibre-gl';
import { MapPinOff } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';

import type { AppLanguage } from '@/lib/format';
import { useAppLanguage } from '@/lib/useAppLanguage';

/**
 * Orientation basemap (MapLibre GL JS + a vector tile provider). It draws the
 * provider's own tiles and attribution only: OSRIP adds no markers, centroids,
 * boundaries or values, because no licensed boundary geometry matching the
 * registry is available. Selection happens in the accessible table.
 */

const DEFAULT_STYLE = 'https://tiles.openfreemap.org/styles/positron';
const configured = import.meta.env.VITE_MAP_STYLE_URL;
export const MAP_STYLE_URL: string | null = configured === 'none' ? null : (configured || DEFAULT_STYLE);

// Initial camera only (roughly the extent of Oman); not a boundary and not stored data.
const INITIAL_VIEW: [[number, number], [number, number]] = [[51.8, 16.6], [59.9, 26.5]];
const LOAD_TIMEOUT_MS = 15_000;

type MapState = 'loading' | 'ready' | 'unavailable' | 'disabled';

function labelExpression(language: AppLanguage): ExpressionSpecification {
  return language === 'ar'
    ? ['coalesce', ['get', 'name:ar'], ['get', 'name']]
    : ['coalesce', ['get', 'name:en'], ['get', 'name_en'], ['get', 'name:latin'], ['get', 'name']];
}

function applyLanguage(map: MapLibreMap, language: AppLanguage): void {
  for (const layer of map.getStyle().layers) {
    if (layer.type !== 'symbol') continue;
    const current: unknown = map.getLayoutProperty(layer.id, 'text-field');
    if (current === undefined || !JSON.stringify(current).includes('name')) continue;
    map.setLayoutProperty(layer.id, 'text-field', labelExpression(language));
  }
}

export function Basemap({ label }: { label: string }) {
  const { t } = useTranslation();
  const language = useAppLanguage();
  const container = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const languageRef = useRef(language);
  const [state, setState] = useState<MapState>(MAP_STYLE_URL ? 'loading' : 'disabled');
  const [tilesFailing, setTilesFailing] = useState(false);

  useEffect(() => {
    languageRef.current = language;
    const map = mapRef.current;
    if (map && state === 'ready') applyLanguage(map, language);
  }, [language, state]);

  useEffect(() => {
    if (!MAP_STYLE_URL || !container.current) return undefined;
    const styleUrl = MAP_STYLE_URL;
    let cancelled = false;
    let loaded = false;
    const timer = window.setTimeout(() => {
      if (!cancelled && !loaded) setState('unavailable');
    }, LOAD_TIMEOUT_MS);

    import('./maplibre')
      .then(({ maplibregl, ensureRtlTextPlugin }) => {
        if (cancelled || !container.current) return;
        ensureRtlTextPlugin();
        const map = new maplibregl.Map({
          container: container.current,
          style: styleUrl,
          bounds: INITIAL_VIEW,
          fitBoundsOptions: { padding: 16 },
          attributionControl: { compact: false },
          cooperativeGestures: true,
          dragRotate: false,
          touchPitch: false,
          pitchWithRotate: false,
        });
        mapRef.current = map;
        map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right');
        map.on('load', () => {
          loaded = true;
          if (cancelled) return;
          applyLanguage(map, languageRef.current);
          setState('ready');
        });
        map.on('error', () => {
          if (cancelled) return;
          if (loaded) setTilesFailing(true);
          else setState('unavailable');
        });
      })
      .catch(() => {
        // WebGL unavailable, the module failed to load, or the provider is unreachable.
        if (!cancelled) setState('unavailable');
      });

    return () => {
      cancelled = true;
      window.clearTimeout(timer);
      mapRef.current?.remove();
      mapRef.current = null;
    };
  }, []);

  if (state === 'disabled' || state === 'unavailable') {
    return (
      <div role="status" data-testid="map-unavailable" data-state={state}
        className="flex min-h-48 flex-col items-start gap-2 rounded-lg border border-dashed border-border-strong/50 bg-card/60 p-6 sm:flex-row sm:gap-4">
        <span className="flex size-10 shrink-0 items-center justify-center rounded-full bg-sand-subtle text-sand-foreground">
          <MapPinOff aria-hidden="true" className="size-5" />
        </span>
        <div className="flex flex-col gap-1">
          <p className="font-semibold">{t('pages.geography.mapUnavailableTitle')}</p>
          <p className="max-w-prose text-sm text-muted-foreground">
            {state === 'disabled' ? t('pages.geography.mapDisabled') : t('pages.geography.mapUnavailable')}
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-2">
      <div className="relative overflow-hidden rounded-lg border border-border bg-muted">
        <div ref={container} role="region" aria-label={label} data-testid="basemap" data-state={state}
          className="h-80 w-full sm:h-96" />
        {state === 'loading' ? (
          <p role="status" className="absolute inset-0 flex items-center justify-center text-sm text-muted-foreground">
            {t('pages.geography.mapLoading')}
          </p>
        ) : null}
      </div>
      {tilesFailing ? <p role="status" className="text-xs text-muted-foreground">{t('pages.geography.tilesFailing')}</p> : null}
    </div>
  );
}
