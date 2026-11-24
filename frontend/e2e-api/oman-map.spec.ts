import { expect, test, type Page } from '@playwright/test';

// The Oman map on the full stack, with no external map service: every request leaving localhost
// is stopped and recorded. The configured basemap (playwright.api.config.ts) is not a map style,
// so the map falls back to a plain background unless a test serves a stand-in style for it.
// MapTiler is covered by oman-map-maptiler.spec.ts.

const STUB_STYLE = {
  version: 8,
  name: 'test basemap',
  glyphs: 'https://glyphs.osrip-test.invalid/{fontstack}/{range}.pbf',
  sources: {},
  layers: [{ id: 'background', type: 'background', paint: { 'background-color': '#efe9e1' } }],
};

/** Stops and records requests to other hosts; the routes registered later take precedence. */
async function offline(page: Page): Promise<string[]> {
  const external: string[] = [];
  await page.route(/^https?:\/\/(?!localhost[:/]|127\.0\.0\.1[:/])/, (route) => {
    external.push(route.request().url());
    return route.abort();
  });
  await page.route('https://glyphs.osrip-test.invalid/**', (route) => route.fulfill({ status: 404, body: '' }));
  return external;
}

/** The codes of the areas the map draws now (from MapLibre's rendered features). */
async function drawn(page: Page): Promise<string[]> {
  return page.evaluate(() => {
    const m = (document.querySelector('[data-testid="oman-map-canvas"]') as HTMLElement & { osripMap: import('maplibre-gl').Map }).osripMap;
    return [...new Set(m.queryRenderedFeatures({ layers: ['osrip-fill'] }).map((f) => String(f.properties.code)))];
  });
}

/** Opens the Geography page at the map; false when this browser cannot draw WebGL maps. */
async function openMap(page: Page, query = ''): Promise<boolean> {
  await page.goto(`/geography${query}`);
  const canvas = page.getByTestId('oman-map-canvas');
  const unavailable = page.getByTestId('oman-map-unavailable');
  await expect(canvas.or(unavailable)).toBeVisible();
  if (await unavailable.isVisible()) return false;
  await canvas.scrollIntoViewIfNeeded();
  await expect(canvas).toHaveAttribute('data-state', /ready|unavailable/, { timeout: 30_000 });
  return (await canvas.getAttribute('data-state')) === 'ready';
}

test('boundary files cover every registry area under its own code, Musandam and the enclave included', async ({ page }) => {
  const registry = (await (await page.request.get('/api/v1/areas')).json()) as {
    areas: { code: string; level: string; name_en: string; name_ar: string }[];
  };
  type Collection = { features: { properties: Record<string, string>; geometry: { type: string; coordinates: number[][][][] } }[] };
  const load = async (file: string) => (await (await page.request.get(`/geo/${file}`)).json()) as Collection;
  const [governorates, wilayats, labels, national, mask] = await Promise.all(
    ['oman-governorates.geojson', 'oman-wilayats.geojson', 'oman-labels.geojson', 'oman-national.geojson', 'oman-mask.geojson'].map(load),
  );
  for (const [level, collection, count] of [['governorate', governorates, 11], ['wilayat', wilayats, 63]] as const) {
    const expected = registry.areas.filter((a) => a.level === level).map((a) => a.code).sort();
    expect(expected).toHaveLength(count);
    expect(collection.features.map((f) => f.properties.code).sort()).toEqual(expected);
  }
  // One label per area, named as the registry names it, in both languages.
  const byCode = new Map(registry.areas.map((a) => [a.code, a]));
  expect(labels.features).toHaveLength(74);
  for (const { properties: p } of labels.features) {
    expect(byCode.get(p.code!)?.name_en, p.code).toBe(p.name_en);
    expect(byCode.get(p.code!)?.name_ar, p.code).toBe(p.name_ar);
  }
  // The national outline is the dissolved governorates, not a rectangle: separate parts
  // (Musandam lies apart from the mainland) and a hole (the Nahwa enclave inside Madha).
  const outline = national.features[0]!.geometry;
  expect(outline.type).toBe('MultiPolygon');
  expect(outline.coordinates.length).toBeGreaterThan(1);
  expect(outline.coordinates.some((polygon) => polygon.length > 1)).toBe(true);
  const lats = outline.coordinates.flatMap((polygon) => polygon[0]!.map(([, lat]) => lat!));
  expect(Math.max(...lats)).toBeGreaterThan(26.3); // Musandam
  expect(Math.min(...lats)).toBeLessThan(16.8); // Dhofar
  expect(mask.features.length).toBeGreaterThan(0);
});

test('an unreachable basemap falls back to the boundaries on a plain background', async ({ page }) => {
  const external = await offline(page);
  test.skip(!(await openMap(page)), 'this browser cannot draw WebGL maps');
  const map = page.getByTestId('oman-map');
  await expect(map).toHaveAttribute('data-provider', 'plain');
  await expect(page.getByTestId('map-fallback')).toContainText('did not respond or refused the request');
  await expect(page.getByTestId('map-provider')).toContainText('No basemap');
  await expect(page.getByTestId('map-toolbar')).toBeVisible();
  // Satellite needs MapTiler; relief and 3D need a terrain source, which the plain map has not.
  await expect(page.getByTestId('map-view-satellite')).toBeDisabled();
  await expect(page.getByTestId('map-3d')).toBeDisabled();
  await expect(page.getByTestId('map-key-note')).toBeVisible();
  await expect(page.getByTestId('map-legend')).toContainText('No data');
  // Nothing but label fonts was asked of another host (and that was stopped here).
  expect(external.filter((u) => !u.startsWith('https://tiles.openfreemap.org/fonts/'))).toEqual([]);
});

test('with a basemap: views, relief and 3D, hover, and a governorate with only its own wilayats', async ({ page }) => {
  const external = await offline(page);
  const warnings: string[] = [];
  page.on('console', (m) => { if (m.type() === 'warning') warnings.push(m.text()); });
  await page.route('**/__no_map_style__.json', (route) => route.fulfill({ json: STUB_STYLE }));
  test.skip(!(await openMap(page)), 'this browser cannot draw WebGL maps');
  const map = page.getByTestId('oman-map');
  await expect(map).toHaveAttribute('data-provider', 'openfreemap');
  await expect(page.getByTestId('map-fallback')).toHaveCount(0);
  await expect(map).toHaveAttribute('data-view', 'topographic');
  await expect(page.getByTestId('map-view-satellite')).toBeDisabled();
  await expect(page.getByTestId('map-view-satellite')).toHaveAttribute('title', /MapTiler key/);

  // Terrain view, remembered for the next visit.
  await page.getByTestId('map-view-terrain').click();
  await expect(map).toHaveAttribute('data-view', 'terrain');
  await expect(page.getByTestId('map-view-terrain')).toHaveAttribute('aria-checked', 'true');
  expect(await page.evaluate(() => localStorage.getItem('osrip.map.view'))).toBe('terrain');

  // 3D only on request; relief comes from the open Terrain Tiles.
  await page.getByTestId('map-3d').click();
  await expect(map).toHaveAttribute('data-3d', 'true');
  await expect(page.getByTestId('map-3d')).toHaveAttribute('aria-pressed', 'true');
  await expect.poll(() => external.some((u) => u.startsWith('https://elevation-tiles-prod.s3.amazonaws.com/terrarium/'))).toBe(true);
  // The relief and the 3D terrain have separate sources, as MapLibre advises.
  expect(warnings.filter((w) => w.includes('same source for a hillshade'))).toEqual([]);
  await page.getByTestId('map-3d').click();
  await expect(map).not.toHaveAttribute('data-3d', 'true');
  await page.getByTestId('map-reset').click();

  // The middle of the map is inside Oman: hover names the area, a click selects it.
  const box = (await page.getByTestId('oman-map-canvas').boundingBox())!;
  await expect(async () => {
    await page.mouse.move(box.x + box.width / 2 - 5, box.y + box.height / 2);
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
    await expect(page.getByTestId('map-tooltip')).toBeVisible({ timeout: 1000 });
  }).toPass();
  await expect(page.getByTestId('map-tooltip')).toContainText(/No data|published/);
  // At first the eleven governorates only: no wilayat is drawn, labelled or clickable.
  await expect(map).toHaveAttribute('data-level', 'governorate');
  expect(await drawn(page)).toHaveLength(11);
  await page.mouse.click(box.x + box.width / 2, box.y + box.height / 2);
  await expect(page).toHaveURL(/area=OM-/);
  await expect(page.getByTestId('selected-area')).toBeVisible();
  // A governorate clicked on the map becomes the focus: its own wilayats, and only those.
  await expect(map).toHaveAttribute('data-level', 'wilayat');
  const clicked = (await map.getAttribute('data-focus'))!;
  expect(clicked).toMatch(/^OM-[A-Z]{2}$/);
  for (const code of await drawn(page)) expect(code.startsWith(`${clicked}-`)).toBe(true);

  // Dhofar: its ten wilayats on the map (fill, outlines, labels, click targets) and in the list.
  await page.getByTestId('map-governorate').selectOption('OM-ZU');
  await expect(map).toHaveAttribute('data-focus', 'OM-ZU');
  await expect(map).toHaveAttribute('data-shown', '10');
  await expect(page).toHaveURL(/governorate=OM-ZU/);
  const filters = await page.evaluate(() => {
    const m = (document.querySelector('[data-testid="oman-map-canvas"]') as HTMLElement & { osripMap: import('maplibre-gl').Map }).osripMap;
    return { fill: m.getFilter('osrip-fill'), labels: m.getFilter('osrip-labels'), focus: m.getFilter('osrip-focus') };
  });
  const listed = (filters.fill as [string, unknown, [string, string[]]])[2][1];
  expect(listed).toHaveLength(10);
  expect(listed.every((c) => c.startsWith('OM-ZU-'))).toBe(true);
  expect(JSON.stringify(filters.labels)).toContain('"OM-ZU-01"');
  expect(JSON.stringify(filters.labels)).not.toContain('"OM-MA-');
  expect(filters.focus).toEqual(['==', ['get', 'code'], 'OM-ZU']);
  await expect.poll(async () => (await drawn(page)).every((c) => c.startsWith('OM-ZU-'))).toBe(true);
  const wilayats = page.getByTestId('map-wilayat').locator('option');
  await expect(wilayats).toHaveCount(11); // the whole governorate and its ten wilayats
  await expect(page.getByTestId('map-focus-status')).toHaveText('Showing Dhofar and its 10 wilayats only.');
  await expect(page.locator('#compare-heading')).toHaveText('Compare the wilayats of Dhofar');
  await expect(page.getByTestId('governorate-comparison')).toHaveAttribute('data-level', 'wilayat');
  // Only Dhofar's wilayats in the table below the map.
  const rows = page.getByTestId('area-table').locator('tbody tr');
  await expect(rows).toHaveCount(11);
  for (const code of await rows.evaluateAll((r) => r.map((x) => (x as HTMLElement).dataset.code ?? ''))) expect(code.startsWith('OM-ZU')).toBe(true);

  // A wilayat: highlighted alone, with its own data or "No published wilayat data".
  await page.getByTestId('map-wilayat').selectOption('OM-ZU-01');
  await expect(page).toHaveURL(/area=OM-ZU-01/);
  await expect(page.getByTestId('selected-area')).toHaveAttribute('data-area', 'OM-ZU-01');
  await expect(page.getByTestId('area-no-data').or(page.getByTestId('area-observations'))).toBeVisible();

  // Another governorate resets the wilayat and what depended on it.
  await page.getByTestId('map-governorate').selectOption('OM-MA');
  await expect(page.getByTestId('map-wilayat')).toHaveValue('');
  await expect(page).not.toHaveURL(/area=OM-ZU/);
  await expect(map).toHaveAttribute('data-shown', '6');
  await expect(page.getByTestId('selected-area')).toHaveAttribute('data-area', 'OM-MA');
  // Back to all governorates.
  await page.getByTestId('map-all-governorates').click();
  await expect(map).toHaveAttribute('data-level', 'governorate');
  await expect(map).not.toHaveAttribute('data-focus', /.+/);

  // The data mode can be switched on the map itself.
  await page.getByTestId('map-data-mode').getByText('Synthetic').click();
  await expect(page).toHaveURL(/mode=synthetic/);
});

test('Arabic: the toolbar at the start edge and the zoom buttons opposite it', async ({ page }) => {
  await offline(page);
  await page.route('**/__no_map_style__.json', (route) => route.fulfill({ json: STUB_STYLE }));
  await page.addInitScript(() => localStorage.setItem('osrip.language', 'ar'));
  test.skip(!(await openMap(page)), 'this browser cannot draw WebGL maps');
  await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
  const canvas = (await page.getByTestId('oman-map-canvas').boundingBox())!;
  const toolbar = (await page.getByTestId('map-toolbar').boundingBox())!;
  expect(toolbar.x + toolbar.width).toBeGreaterThan(canvas.x + canvas.width - 20);
  await expect(page.locator('.maplibregl-ctrl-top-left .maplibregl-ctrl-zoom-in')).toHaveCount(1);
  await expect(page.getByTestId('map-view-terrain')).toContainText('تضاريس');
});
