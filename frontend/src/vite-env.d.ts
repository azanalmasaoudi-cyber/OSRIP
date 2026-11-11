/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_DATA_ADAPTER?: 'mock' | 'http';
  readonly VITE_API_BASE_URL?: string;
  /** Basemap style JSON URL; "none" disables the map (the table remains). */
  readonly VITE_MAP_STYLE_URL?: string;
  /** MapTiler Cloud browser key (restricted to the site's origins in the MapTiler account).
   * Optional: without it the map uses OpenFreeMap and the open Terrain Tiles. */
  readonly VITE_MAPTILER_KEY?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
