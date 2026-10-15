/**
 * Loaded on demand by the Basemap so the map library, its stylesheet and the
 * right-to-left text plugin are only fetched on the Geography page.
 */
import 'maplibre-gl/dist/maplibre-gl.css';

import * as maplibregl from 'maplibre-gl';

// Shapes Arabic labels correctly (BSD-2-Clause, served from this site). The package's
// "exports" hide its prebuilt file, so it is referenced by path.
import rtlTextPluginUrl from '../../../node_modules/@mapbox/mapbox-gl-rtl-text/dist/mapbox-gl-rtl-text.js?url';
// MapLibre locates its worker relative to its own module, which bundling breaks; Vite
// builds the worker (with its shared chunk) as one file and hands over its URL.
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url';

maplibregl.setWorkerUrl(workerUrl);

let rtlRequested = false;

export function ensureRtlTextPlugin(): void {
  if (rtlRequested || maplibregl.getRTLTextPluginStatus() !== 'unavailable') return;
  rtlRequested = true;
  // lazy = true: fetched only when a right-to-left label is first drawn.
  maplibregl.setRTLTextPlugin(rtlTextPluginUrl, true).catch(() => {
    // Labels still render, only without Arabic shaping; the table is unaffected.
  });
}

export { maplibregl };
