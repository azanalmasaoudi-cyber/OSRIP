/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_DATA_ADAPTER?: 'mock' | 'http';
  readonly VITE_API_BASE_URL?: string;
  /** Basemap style JSON URL; "none" disables the map (the table remains). */
  readonly VITE_MAP_STYLE_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
