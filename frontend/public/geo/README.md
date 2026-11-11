# Oman boundaries for the map

| File | Contents |
|---|---|
| `oman-governorates.geojson` | 11 governorates, feature id = registry code (ISO 3166-2, e.g. `OM-ZU`) |
| `oman-wilayats.geojson` | 63 wilayats, feature id = registry code (`OM-XX-NN`, assigned by OSRIP) |
| `oman-national.geojson` | The national outline (one MultiPolygon, Musandam and the other exclaves included) |
| `oman-mask.geojson` | The world with Oman cut out, plus the Nahwa enclave: the map dims everything outside Oman |
| `oman-labels.geojson` | One label point per governorate and wilayat: code, level, and the registry's English and Arabic names |
| `boundaries-report.json` | Every match with its name similarity, corrections, anything unmatched, and the outline check |

Rings follow RFC 7946: outer rings anticlockwise, holes clockwise.

## Source and licence

- **Source:** OpenStreetMap administrative boundaries (`admin_level` 4 for governorates, 6 for
  wilayats), read through the Overpass API on 1 November 2026. The query is stored in the report.
- **Licence:** © OpenStreetMap contributors, [Open Database Licence 1.0](https://opendatacommons.org/licenses/odbl/1-0/).
  These files are a derived database and are offered under the same licence. The map shows the
  attribution "© OpenStreetMap contributors (boundaries, ODbL)".
- **Use:** for orientation and choropleths only. The geometry is simplified (Douglas–Peucker,
  about 200 m for governorates and 100 m for wilayats, coordinates rounded to about 11 m). It is
  not an official boundary and must not be used for legal or survey purposes.

## Checked against the registry

The registry lists 11 governorates and 63 wilayats (Ministry of Finance listing, with the 2022
changes; see the Geography page). The extraction matched all of them, one-to-one:

- **Governorates:** all 11 by their ISO 3166-2 tag in OpenStreetMap.
- **Wilayats:** all 63 by name, within the governorate that the OSM `ref` prefix gives. Eight
  matches have lower name similarity only because of transliteration. They were checked by hand:
  Al Amirat / al Amerat, Boushar / Bawshar, Al Kabil / Al Qabil, Dima W'attayeen / Dama wa at
  Ta'ieen, Al Jazer / Al Jazir, Yankul / Yanqul, Al Mazyona / Al Mazyunah, and Shalim and the
  Hallaniyat Islands / Shalim Wa Juzor Al Hallaniyat.
- **One correction:** OSM relation 19558488 (`ref` 0801) is named "Jalaan Bani Bu ALi", but its
  polygon contains the town of Sur. The Jaalan Bani Bu Ali boundary is relation 19558567 (`ref`
  0804). Relation 19558488 is therefore used for **Sur (OM-SJ-01)**. The correction is listed in
  the report, and it could be reported upstream to OpenStreetMap.

## The national outline, mask and labels

- **Outline:** dissolved from the same governorate relations, not drawn as a rectangle and not
  fetched separately. A boundary way used by exactly one governorate lies on the national edge; a
  way shared by two governorates is an internal border and is dropped. The edge ways are joined
  into rings (38 parts: the mainland, Musandam, Madha and the islands) and a ring inside another
  becomes a hole: the Nahwa enclave, which belongs to the United Arab Emirates although Madha
  surrounds it. The report records the parts, the holes and any segment that could not be joined
  (0).
- **Mask:** one world polygon with every part of Oman cut out of it, and Nahwa as a separate
  polygon, so the map dims everything that is not Oman.
- **Labels:** each area's label point is the point inside its largest part that lies furthest from
  its edge (a coarse-to-fine grid search), so a label never falls outside a crescent-shaped area.
  Names come from the registry, not from OpenStreetMap.

Coastal boundaries in OpenStreetMap may extend to the territorial sea. The map draws the shading
beneath the basemap's water, so the sea covers those parts. Without the basemap, they stay visible.

## Rebuilding

```bash
python scripts/build_boundaries.py fetch osm.json   # from backend/, one Overpass request
python scripts/build_boundaries.py build osm.json   # needs OSRIP_DATABASE_URL for the registry
```

`build` writes all five GeoJSON files. Check `boundaries-report.json` after every rebuild. It must
list no unmatched area on either side and no unjoined outline segment, and any new low-similarity
match needs checking by hand. `backend/tests/test_build_boundaries.py` tests the dissolve, the
ring orientation and the label points; `frontend/e2e-api/oman-map.spec.ts` checks the published
files against the registry.
