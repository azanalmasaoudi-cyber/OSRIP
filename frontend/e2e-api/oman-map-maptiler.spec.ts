import { expect, test, type Page } from '@playwright/test';

// The MapTiler path, on a web server built with a placeholder key (the "maptiler" project in
// playwright.api.config.ts). No request reaches MapTiler or any other map host: each is answered
// here by a stand-in or stopped, so this checks which styles, terrain and logo OSRIP asks for and
// how it falls back, not MapTiler's service itself (that needs a real key; docs/MAP.md).

const KEY = 'e2e-placeholder-not-a-key';
const style = (name: string) => ({
  version: 8,
  name,
  glyphs: `https://api.maptiler.com/fonts/{fontstack}/{range}.pbf?key=${KEY}`,
  sources: {},
  layers: [{ id: 'background', type: 'background', paint: { 'background-color': '#efe9e1' } }],
});
const LOGO = '<svg xmlns="http://www.w3.org/2000/svg" width="80" height="20"><rect width="80" height="20" fill="#f4a873"/></svg>';

interface Traffic { styles: string[]; terrain: string[]; external: string[] }

/** Answers the map hosts; `maptiler` and `openfreemap` choose how each style request is answered. */
async function serve(page: Page, { maptiler = 200, openfreemap = 200 }: { maptiler?: number; openfreemap?: number } = {}): Promise<Traffic> {
  const traffic: Traffic = { styles: [], terrain: [], external: [] };
  await page.addInitScript(() => localStorage.setItem('osrip.intro.autoplay', 'off'));
  await page.route(/^https?:\/\/(?!localhost[:/]|127\.0\.0\.1[:/])/, (route) => {
    traffic.external.push(route.request().url());
    return route.abort();
  });
  await page.route('https://api.maptiler.com/**', (route) => {
    const url = route.request().url();
    traffic.external.push(url);
    if (url.includes('/style.json')) {
      traffic.styles.push(url);
      return maptiler === 200 ? route.fulfill({ json: style('maptiler stand-in') }) : route.fulfill({ status: maptiler, body: '' });
    }
    if (url.includes('/tiles/terrain-rgb-v2/tiles.json')) {
      traffic.terrain.push(url);
      return route.fulfill({ json: { tilejson: '2.2.0', tiles: [`https://api.maptiler.com/tiles/terrain-rgb-v2/{z}/{x}/{y}.webp?key=${KEY}`], maxzoom: 12 } });
    }
    if (url.includes('/resources/logo.svg')) return route.fulfill({ contentType: 'image/svg+xml', body: LOGO });
    return route.fulfill({ status: 404, body: '' }); // tiles and fonts: not needed here
  });
  await page.route('https://tiles.openfreemap.org/styles/**', (route) => {
    traffic.styles.push(route.request().url());
    return openfreemap === 200 ? route.fulfill({ json: style('openfreemap stand-in') }) : route.fulfill({ status: openfreemap, body: '' });
  });
  return traffic;
}

async function openMap(page: Page): Promise<boolean> {
  await page.goto('/geography');
  const canvas = page.getByTestId('oman-map-canvas');
  const unavailable = page.getByTestId('oman-map-unavailable');
  await expect(canvas.or(unavailable)).toBeVisible();
  if (await unavailable.isVisible()) return false;
  await canvas.scrollIntoViewIfNeeded();
  await expect(canvas).toHaveAttribute('data-state', /ready|unavailable/, { timeout: 30_000 });
  return (await canvas.getAttribute('data-state')) === 'ready';
}

test('a MapTiler key: MapTiler styles for each view, its logo, and MapTiler terrain for 3D', async ({ page }) => {
  const traffic = await serve(page);
  test.skip(!(await openMap(page)), 'this browser cannot draw WebGL maps');
  const map = page.getByTestId('oman-map');
  await expect(map).toHaveAttribute('data-provider', 'maptiler');
  await expect(page.getByTestId('map-provider')).toContainText('MapTiler');
  await expect(page.getByTestId('maptiler-logo')).toBeVisible();
  await expect(page.getByTestId('map-key-note')).toHaveCount(0);
  expect(traffic.styles[0]).toBe(`https://api.maptiler.com/maps/topo-v4/style.json?key=${KEY}`);

  await expect(page.getByTestId('map-view-satellite')).toBeEnabled();
  await page.getByTestId('map-view-satellite').click();
  await expect(map).toHaveAttribute('data-view', 'satellite');
  await expect.poll(() => traffic.styles.at(-1)).toContain('/maps/hybrid-v4/style.json');
  await page.getByTestId('map-view-terrain').click();
  await expect.poll(() => traffic.styles.at(-1)).toContain('/maps/landscape-v4/style.json');

  // MapTiler's styles carry their own relief, so no terrain is requested until 3D is switched on.
  expect(traffic.terrain).toEqual([]);
  await page.getByTestId('map-3d').click();
  await expect(map).toHaveAttribute('data-3d', 'true');
  await expect.poll(() => traffic.terrain.length).toBeGreaterThan(0);
  expect(traffic.terrain[0]).toBe(`https://api.maptiler.com/tiles/terrain-rgb-v2/tiles.json?key=${KEY}`);

  // The key goes to MapTiler and nowhere else.
  const leaked = traffic.external.filter((u) => u.includes(KEY) && !u.startsWith('https://api.maptiler.com/'));
  expect(leaked).toEqual([]);
});

test('the dark theme asks for MapTiler dark styles', async ({ page }) => {
  const traffic = await serve(page);
  await page.addInitScript(() => localStorage.setItem('osrip.theme', 'dark'));
  test.skip(!(await openMap(page)), 'this browser cannot draw WebGL maps');
  expect(traffic.styles[0]).toContain('/maps/topo-v4-dark/style.json');
});

for (const status of [403, 429]) {
  test(`MapTiler refusing the key (${status}) hands over to OpenFreeMap`, async ({ page }) => {
    const traffic = await serve(page, { maptiler: status });
    test.skip(!(await openMap(page)), 'this browser cannot draw WebGL maps');
    const map = page.getByTestId('oman-map');
    await expect(map).toHaveAttribute('data-provider', 'openfreemap');
    await expect(page.getByTestId('map-fallback')).toBeVisible();
    await expect(page.getByTestId('maptiler-logo')).toHaveCount(0);
    await expect(page.getByTestId('map-view-satellite')).toBeDisabled();
    expect(traffic.styles.some((u) => u.startsWith('https://tiles.openfreemap.org/styles/positron'))).toBe(true);
  });
}

test('when MapTiler and OpenFreeMap both fail, the boundaries stay on a plain background', async ({ page }) => {
  await serve(page, { maptiler: 503, openfreemap: 503 });
  test.skip(!(await openMap(page)), 'this browser cannot draw WebGL maps');
  await expect(page.getByTestId('oman-map')).toHaveAttribute('data-provider', 'plain');
  await expect(page.getByTestId('map-fallback')).toBeVisible();
  await expect(page.getByTestId('map-legend')).toContainText('No data');
});
