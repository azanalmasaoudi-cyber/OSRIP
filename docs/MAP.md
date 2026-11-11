# The Oman geographic intelligence map

The Geography page shows the Sultanate of Oman, Musandam included, as a choropleth of its 11
governorates and 63 wilayats, with Arabic and English names. Code:
`frontend/src/components/geography/OmanMap.tsx` (the map) and `mapProviders.ts` (where the map
comes from); boundary data: `frontend/public/geo/` (see its README).

## What it does

| Feature | How |
|---|---|
| Views | Topographic, Satellite (with roads and names), Terrain. The choice is remembered in the browser. |
| Relief | MapTiler styles carry their own hillshading. Without MapTiler, a hillshade from the open Terrain Tiles. |
| 3D | Off until the 3D button is pressed; then terrain elevation (exaggerated 1.4×), tilt and rotation. |
| Themes | Light and dark basemaps and overlays follow the app's theme. |
| Oman only | The camera is held to the region around Oman; everything outside the national outline is dimmed; the outline is drawn. |
| Areas | Governorates or wilayats; hover outlines and names an area, a click selects it (the page shows its details and the map zooms to it); "Show all of Oman" resets. |
| Statistics | Shading by published values per area or by a compared indicator; axis, indicator, period and data mode (verified or synthetic) are chosen on the page. |
| Languages | Labels in Arabic or English with the interface; toolbar at the start edge, zoom buttons opposite (right-to-left in Arabic). |

**Values.** An area is shaded only from observations published for exactly that area. An area
without one is "No data" (neutral grey), never zero. Wilayat values are never estimated by sharing
out a governorate's or the nation's total; today no indicator is published per wilayat, so the
wilayat level reads "No data" and says why.

## Providers and fallback

The map tries each provider in turn and moves to the next when one fails: no response, a refused
key or origin (401, 403), the quota reached (429) or a server error (5xx). A missing tile does not
count. The page then says that the preferred provider did not respond.

| Order | Provider | When | Topographic | Satellite | Terrain | Relief and 3D |
|---|---|---|---|---|---|---|
| 1 | MapTiler Cloud | `VITE_MAPTILER_KEY` is set | `topo-v4` / `topo-v4-dark` | `hybrid-v4` / `hybrid-v4-dark` | `landscape-v4` / `landscape-v4-dark` | `terrain-rgb-v2` |
| 2 | OpenFreeMap | unless `VITE_MAP_STYLE_URL=none` | Positron / Dark | not available | same as Topographic | open Terrain Tiles |
| 3 | Plain background | always | boundaries only | not available | boundaries only | not available |

The MapTiler style names are those of MapTiler's own client library (`@maptiler/client` 3.1.0).
With MapTiler, the MapTiler logo is shown on the map, as its terms require (MapLibre does not add
it; MapTiler's own SDK would).

## Setting up MapTiler

Nothing below costs money, and none of it has been done for this deployment. A key is needed
before MapTiler can be tried at all; **live MapTiler has not been tested with OSRIP yet.** The
tests check the requests OSRIP makes and its fallback, with stand-in responses
(`frontend/e2e-api/oman-map-maptiler.spec.ts`).

1. Create an account at <https://cloud.maptiler.com/> (the Free plan needs no payment card).
2. Open **API keys** and create a key for the deployed site, e.g. "OSRIP production".
3. In that key's settings, under **Allowed HTTP origins**, add only the site's domain (the value of
   `OSRIP_DOMAIN`). MapTiler then refuses requests from any other site, and requests without an
   origin. Do not allow `localhost` on this key.
4. For development, create a second key ("OSRIP local") that allows only `localhost`.
5. Put the key in the environment, never in the code:
   - deployment: `VITE_MAPTILER_KEY=<key>` in `deploy/.env`, then rebuild the web image
     (`docker compose -f deploy/docker-compose.yml --env-file deploy/.env up -d --build web`). The
     key is compiled into the interface, so changing it needs a rebuild;
   - development: `VITE_MAPTILER_KEY=<local key>` in `frontend/.env.local` (not committed), then
     restart the development server.
6. Open the Geography page. The note under the map should name MapTiler, the Satellite button
   should be enabled, and the MapTiler logo should show. If the page says it fell back, check the
   key's allowed origins.
7. Check usage under **Analytics** in the MapTiler account during the first days.

**The key is public by design.** Every visitor's browser reads it, as with any web map key. It is
protected by its allowed origins, not by secrecy. That is why it is the one `VITE_` variable
allowed to hold a key: `deploy/predeploy_check.py` accepts it but warns that it must be
restricted. Every other key stays on the server.

## Environment variables

| Variable | Where | Default | Meaning |
|---|---|---|---|
| `VITE_MAPTILER_KEY` | `deploy/.env` (build argument), `frontend/.env.local` | empty | MapTiler browser key. Empty: OpenFreeMap and open terrain. |
| `VITE_MAP_STYLE_URL` | same | OpenFreeMap Positron | The fallback basemap style (https://), or `none` for no basemap (boundaries on a plain background). With a custom URL, the Content-Security-Policy must allow its host. |

The Content-Security-Policy in `deploy/Caddyfile` allows exactly these map hosts in `img-src` and
`connect-src`: `api.maptiler.com`, `tiles.openfreemap.org` and
`elevation-tiles-prod.s3.amazonaws.com`.

## Data sources

| Data | Source | Licence / terms | Checked |
|---|---|---|---|
| Governorate and wilayat boundaries | OpenStreetMap administrative relations (`admin_level` 4 and 6), Overpass API, 1 November 2026 | © OpenStreetMap contributors, ODbL 1.0 | All 11 + 63 matched one-to-one to the registry; one OSM naming error corrected (`frontend/public/geo/README.md`) |
| National outline, mask, label points | Derived from the boundaries above by `backend/scripts/build_boundaries.py` | ODbL (derived database) | 38 parts, 1 hole (the Nahwa enclave), 0 unjoined segments; every label inside its area; Khasab, Madha, Muscat and Salalah inside, Dubai and Nahwa outside |
| Area names and codes | OSRIP registry: Ministry of Finance listing, Ministry of Interior 2022 changes | Public sources, cited on the Geography page | ISO 3166-2 for governorates; `OM-XX-NN` for wilayats (assigned by OSRIP) |
| Basemap (fallback) | OpenFreeMap, OpenMapTiles schema | Free public service ([terms](https://openfreemap.org/tos/)); data © OpenStreetMap contributors | Attribution on the map |
| Relief (fallback) | Terrain Tiles on AWS Open Data (Mapzen): SRTM on land, ETOPO1 under the sea, among others | Open data, [attribution](https://github.com/tilezen/joerd/blob/master/docs/attribution.md) | Attribution on the map |
| Basemap, imagery, terrain (preferred) | MapTiler Cloud | MapTiler terms; MapTiler and OpenStreetMap attribution (from the style) and the MapTiler logo | Not yet tried with a real key |

The boundaries are simplified and are not official. They serve orientation and choropleths, not
legal or survey use.

## Pricing, limits and usage

As read on MapTiler's pricing page and documentation on 2 November 2026; check
<https://www.maptiler.com/cloud/pricing/> again before deciding.

| Plan | Price | Included per month | Beyond that |
|---|---|---|---|
| Free | $0 | 100,000 API requests, 5,000 sessions (2,000 with 3D), 1 API key, 5 custom styles | Maps are suspended for the rest of the month |
| Flex | $30 a month | 500,000 API requests, 25,000 sessions | $0.15 per 1,000 requests, $2.50 per 1,000 sessions, $6 per 1,000 3D sessions |

- **What counts:** OSRIP uses MapLibre, not MapTiler's SDK, so MapTiler counts **requests**, not
  sessions. A vector tile is 1 request and a rendered 512-pixel raster tile 4; style JSON, TileJSON
  and fonts are free.
- **Free plan terms:** MapTiler describes it as suitable for testing, proofs of concept,
  prototyping, personal or non-commercial use, and it requires the MapTiler logo (shown). A
  commercial or public deployment should be checked against MapTiler's terms; a paid plan is a
  decision for the project owner. OSRIP activates nothing paid.
- **When the quota runs out:** MapTiler refuses requests (429 or 403), and OSRIP falls back to
  OpenFreeMap for the visit.
- **OpenFreeMap and Terrain Tiles** are free and need no key. They publish no usage limit, and
  there is no service-level agreement.

**How OSRIP keeps requests down:**

- The map loads only when it scrolls into view.
- Tiles are not refetched when they expire (`refreshExpiredTiles: false`), and the browser caches
  them.
- There are no world copies, and the camera stays near Oman.
- The 3D terrain source loads only while 3D is on.
- A provider that refuses is not retried.

**Monitoring:** MapTiler's Analytics page shows requests per key and per day. Map requests go
straight from the browser to the provider, so OSRIP's Service Health page does not see them.

## Tests

- `backend/tests/test_build_boundaries.py`: the outline dissolve with a shared way and an enclave,
  ring orientation, the mask, and label points (a C-shape, the largest part).
- `frontend/e2e-api/oman-map.spec.ts` (full stack, every external request stopped):
  - the boundary files against the registry: codes, names and the outline's parts and hole;
  - the fallback to a plain background;
  - with a stand-in basemap: views, remembered view, 3D, hover, selection, the wilayat level, the
    "never estimated" note and the data mode;
  - the Arabic layout.
- `frontend/e2e-api/oman-map-maptiler.spec.ts` (a web server built with a placeholder key; MapTiler
  answered by stand-ins):
  - the style requested for each view and theme, the logo, and the terrain for 3D;
  - the key sent nowhere but MapTiler;
  - the hand-over to OpenFreeMap on 403 and 429, and to the plain background when both fail.

## Limitations

- Live MapTiler is untested until a key exists (see "Setting up MapTiler").
- Without MapTiler there is no satellite imagery. OpenFreeMap's Terrain view is its Topographic
  style; the relief comes from the open hillshade.
- The camera bounds are a box around Oman, wider than the country so that a wide map can show all
  of it. Beyond the outline the map is dimmed, not hidden.
- Coastal boundaries in OpenStreetMap reach into the territorial sea. With a basemap the sea covers
  them; on the plain background they show.
- Labels use the basemap's font. Without a basemap they need OpenFreeMap's font server (or no labels
  are drawn).
- No indicator is published per wilayat yet, so the wilayat choropleth is all "No data" until a
  source publishes wilayat values.
- The map needs WebGL. Without it, the page explains that, and the area table remains the complete,
  accessible view.
