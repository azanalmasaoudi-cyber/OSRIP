# Visual assets register

Every image, typeface and graphic used in the OSRIP interface, with its source,
creator, licence and local file. Update this file in the same change that adds,
replaces or removes an asset. The on-page credits are generated from
`frontend/src/content/photos.ts`; keep the two in sync.

The visual identity (colours, patterns, mark) is a **proposal for an academic
prototype**. It is not official government branding. No official seal, emblem,
logo or flag is used, and no image implies endorsement by any public authority.

## AI Assistant face (release 0.8)

| File | What it is | Tool | Source size | File size used | Native 4K | Rights and labelling |
|---|---|---|---|---|---|---|
| `frontend/public/images/assistant/ai-assistant-face-200.jpg` | Clearly fictional, AI-generated adult Omani man, head and shoulders (dishdasha, kumma), plain ivory background | Canva *generate-image* via the connected Canva integration, 2026-10-02, media `MAHW1qlLO9M` | 1264 × 1264 | 200 × 200 (the connector's preview, unchanged) | No | Generated in the project's Canva account (Canva terms for AI-generated content apply). Not a real person, employee or government representative; always shown with the label "AI Assistant / المساعد الذكي" and a note saying so |

The full-resolution master has **not** been exported: that requires saving a Canva design,
which needs the account owner's approval. The 200-pixel file is enough for the avatar sizes
used (at most 96 CSS pixels, 2× density). Prompt and checksum: `frontend/assets/editorial/sources.json`.

## Landscape image set: status

The booklet illustrations (1536 × 1024 masters) remain in use for electricity, water, trade
and the professional. Canva generated 1680 × 944 versions of the professional, electricity,
water and agriculture/fisheries scenes (not exported, see `docs/INTEGRATIONS.md#canva-visual-production`);
the ports/trade image failed with Canva's credit quota. **No image in the project is native
3840 × 2160.** To finish the set: export the four Canva images from saved designs (owner
approval), regenerate ports/trade when credits allow, and record any 3840 × 2160 export as an
upscale of a 1680 × 944 source. The food-security page keeps its SVG illustration until then.
Generated infrastructure is conceptual and is never presented as a photograph of a real site.

## Photographs

The first six photographs were obtained from Wikimedia Commons on 2026-09-25. Their only
change was resizing to web dimensions and re-encoding as JPEG at quality 80. The electricity
photograph was added on 2026-11-12 and was also cropped (see *Electricity photograph* below).

Location check: each file's description, Commons categories and (where recorded)
embedded GPS coordinates were read, and the thumbnail was viewed to confirm the
subject. "GPS" means the file carries camera coordinates that fall at the stated
place.

| Local file (`frontend/public/images/photos/`) | Subject and location | Creator | Licence | Location evidence | Commons source | Used on |
|---|---|---|---|---|---|---|
| `misfat-al-abriyeen-village.jpg` (2000×1601) | Misfat al Abriyeen village and date-palm terraces, Al Hamra, Ad Dakhiliyah | Broc | [CC0 1.0](https://creativecommons.org/publicdomain/zero/1.0/) | GPS 23.1362, 57.3113; category *Misfah* | [File:Misfat_Al_Abriyeen_Village,_Oman.jpg](https://commons.wikimedia.org/wiki/File:Misfat_Al_Abriyeen_Village,_Oman.jpg) | Landing hero |
| `falaj-misfah.jpg` (1400×1050) | Falaj channel between palms and terrace walls, Misfat al Abriyeen | Ji-Elle | [CC BY-SA 3.0](https://creativecommons.org/licenses/by-sa/3.0/) | Description "Falaj in Misfah (Oman)"; categories *Aflaj in Misfah*, *Falaj in Oman* (no GPS) | [File:Misfah_(6).jpg](https://commons.wikimedia.org/wiki/File:Misfah_(6).jpg) | Landing, Food Security card |
| `bahla-fort.jpg` (1600×682) | Bahla Fort, Ad Dakhiliyah (UNESCO World Heritage Site) | Ekrem Canli | [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/) | Description "UNESCO World Heritage Site Bahla Fort in Oman"; category *Bahla Fort* (no GPS) | [File:Bahla_Fort_2019_(04).jpg](https://commons.wikimedia.org/wiki/File:Bahla_Fort_2019_(04).jpg) | Landing, data-rules band |
| `duqm-port.jpg` (1400×685) | Port of Duqm breakwater and quays, Al Wusta | AbdullahAlMaani | [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/) | GPS 19.6611, 57.7285; categories *Duqm Port*, *Ports and harbours in Oman* | [File:ميناء_الدقم_الجديد.jpg](https://commons.wikimedia.org/wiki/File:%D9%85%D9%8A%D9%86%D8%A7%D8%A1_%D8%A7%D9%84%D8%AF%D9%82%D9%85_%D8%A7%D9%84%D8%AC%D8%AF%D9%8A%D8%AF.jpg) | Landing, Trade card |
| `wahiba-sands.jpg` (1600×900) | Dunes of the Sharqiya (Wahiba) Sands near Al Raka | Francesco Bini (User:Sailko) | [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/) | GPS 22.3611, 58.7714; category *Wahiba Sands* | [File:Al-raka,_dune_del_deserto_Sharqiya_01.jpg](https://commons.wikimedia.org/wiki/File:Al-raka,_dune_del_deserto_Sharqiya_01.jpg) | Landing, prototype-status panel |
| `desalination-al-khaluf.jpg` (1400×1050) | Containerised forward-osmosis desalination plant, Al Khaluf, Al Wusta | Starsend (English Wikipedia) | [CC BY-SA 3.0](https://creativecommons.org/licenses/by-sa/3.0/) | Description names Al Khaluf, Oman; category *Desalination plants in Oman* (no GPS) | [File:Modern_Water_FO_Plant_Al_Khaluf_Oman.jpg](https://commons.wikimedia.org/wiki/File:Modern_Water_FO_Plant_Al_Khaluf_Oman.jpg) | Landing, Energy and Essential Services card |
| `electricity-pylons-oman.jpg` (1598×899), with WebP copies at 800 and 1598 px | Steel lattice electricity pylons carrying high-voltage lines beside a road, Oman (place not recorded) | kaartcam (via Mapillary) | [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/) | Description "Typical electricity pylons in Oman"; category *Electricity pylons in Oman* (no GPS) | [File:Electricity_pylons_in_Oman.png](https://commons.wikimedia.org/wiki/File:Electricity_pylons_in_Oman.png) | Overview, Electricity card only (cropped; see below) |

**Attribution.** CC BY-SA images need visible credit. Each photograph on the
landing page has a caption with the location, creator, licence and a link to the
Commons file. The full list is on **Sources and Methodology → Image credits**
(`/sources#image-credits`). The CC0 hero is credited anyway.

**Share-alike.** The resized CC BY-SA files are adaptations and stay under
their original licences. This does not affect the licence of the OSRIP code.

**People.** No identifiable people appear in any photograph (checked by
viewing each resized file).

### Candidates rejected

Several "falaj" search results on Commons were **outside Oman**, so they were
not used: *Falaj in Al Ain Oasis.jpg* and *Date palm tree irrigation.jpg* (Al
Ain, UAE), *Falaj Al Mualla Tower* (Umm Al Quwain, UAE), and *"The Falaj" –
Traditional irrigation system* / *Shees falaj 02.jpg* (Wadi Shees, Sharjah, UAE).
A photo of Nizwa Fort was also passed over because the national flag is
prominent in the frame, which could suggest official endorsement.

### Gaps: what should still be sourced

- **Electricity infrastructure.** Partly filled on 2026-11-12: electricity pylons in Oman
  (place not recorded; see *Electricity photograph* below). A licensed, location-verified photo
  of an Omani power station or solar or wind site is still wanted.
- **Agriculture with people at work.** If one is added, check that clothing
  and workplaces are shown accurately and respectfully, and get consent or a
  licence that covers identifiable people.

The Misfat al Abriyeen photograph moved from the hero background to a photo band under the hero (2026-09-25); its credit caption is unchanged.

No temporary artwork is in use. If an image has to be withdrawn, replace it
with an abstract illustration marked by the `DemoLabel kind="artwork"`
("Temporary artwork") badge, and list it here until it is replaced.

## Typefaces

| Typeface | Creator | Licence | Package (self-hosted) |
|---|---|---|---|
| IBM Plex Sans | IBM Corp. | SIL Open Font License 1.1 | `@fontsource/ibm-plex-sans` 5.3.0 |
| IBM Plex Sans Arabic | IBM Corp. | SIL Open Font License 1.1 | `@fontsource/ibm-plex-sans-arabic` 5.3.0 |

The fonts are bundled from npm and served by the app itself. No request goes
to a third-party font CDN. Licence text: `frontend/node_modules/@fontsource/*/LICENSE`.

## Maps

| Item | Source | Licence / terms | How attribution is kept |
|---|---|---|---|
| Map library | MapLibre GL JS 6.11.2 (`maplibre-gl`, npm, bundled) | BSD-3-Clause | Library licence in the bundle header |
| Arabic label shaping | `@mapbox/mapbox-gl-rtl-text` 0.4.0 (npm, served by the app) | BSD-2-Clause | Licence in `node_modules/@mapbox/mapbox-gl-rtl-text/LICENSE.md` |
| Basemap tiles, style, fonts (fallback) | OpenFreeMap "positron" and "dark" styles (`https://tiles.openfreemap.org/styles/…`), OpenMapTiles schema | Free public service under the [OpenFreeMap terms](https://openfreemap.org/tos/); data © OpenStreetMap contributors, [ODbL](https://www.openstreetmap.org/copyright) | MapLibre's attribution control shows "OpenFreeMap © OpenMapTiles Data from OpenStreetMap": in full on wide maps, compact (open at first, then an "i" button) on narrow ones |
| Relief and 3D terrain (fallback) | Terrain Tiles on AWS Open Data (Mapzen; SRTM, ETOPO1 and others) | Open data; [attribution](https://github.com/tilezen/joerd/blob/master/docs/attribution.md) | Credited in the attribution control |
| Basemap, satellite imagery, terrain (preferred, optional) | MapTiler Cloud, only when `VITE_MAPTILER_KEY` is set | MapTiler terms; data © OpenStreetMap contributors and MapTiler | The style's attribution, plus the MapTiler logo on the map |
| Boundaries, national outline, label points | OpenStreetMap administrative relations, matched to the registry (`frontend/public/geo/`) | © OpenStreetMap contributors, ODbL (derived database) | "© OpenStreetMap contributors (boundaries, ODbL)" in the attribution control |

Tiles are requested by the viewer's browser when the map scrolls into view; they
are not stored or redistributed by OSRIP. `VITE_MAP_STYLE_URL` changes the fallback
basemap or switches it off (`none`). Sources, setup, limits and costs:
`docs/MAP.md`; how the boundary files were made and checked:
`frontend/public/geo/README.md`.
## Icons

[Lucide](https://lucide.dev) via `lucide-react` 1.48.0, ISC licence.

## Editorial illustrations (raster; booklet Appendix F and Canva)

The machine-readable record is `frontend/public/images/editorial/manifest.json`, built
by `tools/build_editorial_images.py` from `frontend/assets/editorial/sources.json`. It
records origin, generator, date, prompt, source dimensions, transformations and every
derivative's real pixel and byte size. No image contains statistics or labels that
change with language, none shows a named real facility, and the professional is fictional.

| Asset | Source (verified pixels) | Native 4K | Status and use |
|---|---|---|---|
| Omani professional (dishdasha, kumma, green folder) | Booklet Appendix F, 1024 × 1536, SHA-256 `1bc0644d…` | No | In use: landing hero. Derivatives 360/640/1024 px wide (AVIF, WebP, JPEG) |
| Electricity concept | Booklet Appendix F, 1536 × 1024, `106792da…` | No | In use: Energy header (Electricity). 480/800/1200/1536 px |
| Water concept (falaj-inspired) | Booklet Appendix F, 1536 × 1024, `683f38bd…` | No | In use: Energy header (Water); crossfades with Electricity. 480–1536 px |
| Trade concept (port diorama) | Booklet Appendix F, 1536 × 1024, `7962723a…` | No | In use: Trade header. 480–1536 px |
| Professional, electricity, water, food security | Canva generate-image on 2026-10-01, each **1680 × 944** (media IDs in the manifest) | No | Generated in Canva, **not exported yet**: export needs a saved Canva design and the owner's approval. A 3840 × 2160 export would be a 2.29× upscale and must be labelled as such |
| Trade (Canva) | — | — | Generation failed: Canva `quota_exceeded`. The booklet trade illustration stays in use |

Masters (unchanged originals) are kept in `frontend/assets/editorial/masters/` and are
never served; browsers receive only the derivatives, chosen by `srcset`/`sizes`
(verified: a 1366 px desktop loads the 360 px portrait and 480 px header images; a
390 px phone at 2× loads the 640 px portrait). Derivatives are never wider than the
master. The booklet generator and prompts were not recorded and are reported as unknown.

## Original graphics (made for OSRIP, no third-party rights)

| Asset | Where | Notes |
|---|---|---|
| Portrait illustration: adult Omani man in a white dishdasha with furakha (tassel) and an embroidered kumma, in a pointed arch | `frontend/public/images/illustrations/omani-man-dishdasha-kumma.svg`, landing page hero only | Drawn for OSRIP on 2026-09-25 as hand-written SVG (no photograph, no image model, no reference photo of a real person). Rights: project-owned. Labelled on the page as an illustration that does not depict a real person and does not represent the assistant. Alt text in both languages. Chosen instead of a photograph to avoid identifiable-person consent questions. Not reviewed yet by an Omani reviewer for cultural accuracy |
| Sector illustrations: electricity (transmission tower, solar panels, mountains), water (falaj channel, date palms, water drop), food security (date palm with fruit, wheat, woven basket), trade (dhow, port crane, containers) | `frontend/public/images/illustrations/sector-{electricity,water,food,trade}.svg`. Used in the section page headers (from 640 px wide) and, for electricity and water, as floating tiles in the landing hero | Drawn for OSRIP on 2026-09-27 as hand-written SVG in the portrait's style: pointed arch, green lattice, sand frame, copper details. No photograph, image model or traced reference was used. Rights: project-owned. Each image has a `<title>` and `<desc>` saying it is an original illustration, not a photograph or a specific site, plus translated alt text. Where shown with content, it carries a visible "Illustration" label (in the hero tiles it is decorative and hidden from screen readers). Optimized: 2.4–3.2 KB each, loaded lazily except in page headers |
| *(retired 2026-10-01)* | The SVG portrait and the electricity, water and trade SVGs remain in the repository; the food SVG is still in use | The landing hero and the electricity, water and trade page headers now use the raster editorial illustrations below |
| Mark: eight-point star of two overlapping squares | `frontend/public/favicon.svg`, `src/components/brand/BrandMark.tsx` | A generic geometric motif, chosen so it cannot be read as a seal or crest |
| Lattice pattern | `pattern-lattice` utility in `src/index.css` | Inspired by star lattices in carved doors and screens, not traced from any building |
| Crenellation divider | `pattern-crenellation` utility in `src/index.css` | Inspired by the stepped, pointed merlons on Omani fort parapets, not traced from any building |

## Image use from release 2.0 (2026-11-01, branch `redesign/omani-decision-platform`)

Only photographs of real places with a recorded free licence, or the project's own labelled
drawings, are shown. Nothing was downloaded, generated or edited for this release.

| Where | Image | Kind |
|---|---|---|
| Landing hero (full-width background, credit in the corner) | `misfat-al-abriyeen-village.jpg` | Photograph, CC0 1.0 |
| Overview hero | `bahla-fort.jpg` | Photograph, CC BY-SA 4.0 |
| Water (Overview sector cards; until 2026-11-02 also the sector header and dashboard cards) | `desalination-al-khaluf.jpg` | Photograph, CC BY-SA 3.0 |
| Food Security (as for Water) | `falaj-misfah.jpg` | Photograph, CC BY-SA 3.0 |
| Trade (as for Water) | `duqm-port.jpg` | Photograph, CC BY-SA 4.0 |
| Electricity (as for Water) | `illustrations/sector-electricity.svg` until 2026-11-12, then `electricity-pylons-oman.jpg` | Project drawing, labelled "Illustration"; since 2026-11-12 a photograph, CC BY-SA 4.0 |

No longer shown: the generated Omani-professional portrait (landing hero), the booklet's
conceptual electricity, water and trade rasters (sector headers) and the floating sector tiles.
The files stay in the repository. The photographs are at most 2000 px wide (none is a native
4K master); see the release report for which Commons originals could replace them.

## Premium sector artwork (2026-11-02, branch `feature/premium-sector-images`)

Four images supplied by the project owner for OSRIP, each 1672 × 941 px (about 16:9) with its
own Arabic and English title. They are **AI-generated illustrations**, not photographs of
specific Omani sites, and their alt text says so. They replace the sector images on the
dashboard cards and in the sector page headers; the Overview page keeps the credited
photographs above.

| Sector | Original (kept as supplied) | Delivered as |
|---|---|---|
| Electricity | `frontend/public/images/sectors/osrip_electricity.png` (2.0 MB); briefly replaced by the photograph below on 2026-11-12 and restored the same day | WebP 836 px (64 KB) or 1672 px (198 KB) |
| Water | `frontend/public/images/sectors/osrip_water.png` (2.3 MB) | WebP 836 px (87 KB) or 1672 px (278 KB) |
| Food Security | `frontend/public/images/sectors/osrip_food_security.png` (2.5 MB) | WebP 836 px (99 KB) or 1672 px (316 KB) |
| Trade | `frontend/public/images/sectors/osrip_trade.png` (2.1 MB) | WebP 836 px (69 KB) or 1672 px (211 KB) |

- **Display** (`components/brand/SectorArtwork.tsx`): each image is shown whole at its own
  ratio (`object-contain`, width and height set, so nothing shifts while it loads). It is never
  cropped, stretched or covered with text, since the image carries its own title.
- **Delivery:** the browser picks the WebP copy it needs (quality 86–88, made with Pillow), and
  falls back to the original PNG. Dashboard cards load lazily; the sector header loads at once.
- **Rights:** owner-supplied for this project.

## Electricity photograph (2026-11-12)

A real photograph taken in Oman, shown **only on the Overview page**, in the Electricity sector
card, where the project's labelled drawing used to be.

- **History.** It first went in on branch `feature/electricity-oman-photo` (PR #19), which also
  put it on the dashboard cards, the welcome and the electricity page header in place of the
  owner's artwork. At the owner's request that was corrected the same day on branch
  `fix/electricity-photo-overview-only`. The dashboard, welcome and sector pages show the
  original artwork again (`osrip_electricity.png` and its WebP copies, restored byte for byte
  from Git history and identical to `docs/OSRIP_Premium_Sector_Cards/osrip_electricity.png`).
  The page-header thumbnail (`SectorIllustration`, currently unused) shows its labelled
  illustration again.

- **Source:** [File:Electricity_pylons_in_Oman.png](https://commons.wikimedia.org/wiki/File:Electricity_pylons_in_Oman.png)
  on Wikimedia Commons, 1598 × 1153 px PNG, taken on 2017-06-09 by **kaartcam** and imported from
  Mapillary. Licence [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/) (attribution
  required), read from the file's Commons metadata on 2026-11-12. Downloaded the same day from
  `upload.wikimedia.org`; its SHA-1 matched the one Commons publishes
  (`aa267042c4ec9e62573b7f449a65e0f33aaf7369`). The original is not stored in the repository.
- **Location:** Commons records "Oman" only (no coordinates), so the credit names Oman and no town.
- **Changes (disclosed in the credit):** cropped to 16:9 (rows 96–995 of 1153, full width, so both
  pylons stay whole), saved as JPEG (quality 82, 86 KB) and WebP (quality 80: 800 px 15 KB,
  1598 px 36 KB) with Pillow. It is never enlarged. Nothing is written into the image file and
  nothing is laid over it except the credit caption.
- **Files** (`frontend/public/images/photos/`): `electricity-pylons-oman.jpg`,
  `electricity-pylons-oman-800.webp`, `electricity-pylons-oman-1598.webp`. Browsers that read
  WebP get the width they need; others get the JPEG.
- **Where:** only `components/brand/SectorImage.tsx`, which only the Overview page uses. The
  sector artworks (`SectorArtwork.tsx`: dashboard cards, welcome, sector page headers) and the
  labelled illustrations (`SectorIllustration.tsx`) do not use it.
- **Attribution:** the Overview card's caption shows the location, creator and licence and links
  to the Commons file. The full entry under **Sources and Methodology → Image credits** links the
  licence and the file and lists the changes.
- **Share-alike:** the cropped files are an adaptation and are shared under CC BY-SA 4.0. This does
  not affect the licence of the OSRIP code.
- **People:** none identifiable (one distant parked car).
- **Replaced:** on the Overview card, the project's drawing `illustrations/sector-electricity.svg`
  (labelled "Illustration"). The file stays in the repository.
