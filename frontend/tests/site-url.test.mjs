import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';

import { PRIVATE_PREFIXES, PUBLIC_PAGES, publicSiteUrl, robotsTxt, sitemapXml } from '../src/lib/siteUrl.ts';

test('the public address is only one that was really given, over https, never local', () => {
  assert.equal(publicSiteUrl({}), null, 'no address: no canonical link or sitemap');
  assert.equal(publicSiteUrl({ VITE_PUBLIC_SITE_URL: 'https://osrip.example.org/some/path' }), 'https://osrip.example.org');
  // Vercel's own production domain on Vercel's production build only, not on previews.
  assert.equal(publicSiteUrl({ VERCEL_ENV: 'production', VERCEL_PROJECT_PRODUCTION_URL: 'osrip.vercel.app' }), 'https://osrip.vercel.app');
  assert.equal(publicSiteUrl({ VERCEL_ENV: 'preview', VERCEL_PROJECT_PRODUCTION_URL: 'osrip.vercel.app' }), null);
  for (const local of ['http://localhost:5173', 'https://localhost', 'https://127.0.0.1', 'https://app.localhost', 'http://osrip.example.org', 'not a url']) {
    assert.equal(publicSiteUrl({ VITE_PUBLIC_SITE_URL: local }), null, local);
  }
});

test('robots.txt keeps sign-in, account and administration pages out of search results', () => {
  const robots = robotsTxt('https://osrip.vercel.app');
  for (const prefix of ['/admin/', '/account', '/data-management', '/api/']) assert.ok(robots.includes(`Disallow: ${prefix}`), prefix);
  assert.ok(robots.includes('Sitemap: https://osrip.vercel.app/sitemap.xml'));
  assert.ok(!robotsTxt(null).includes('Sitemap'), 'no sitemap line without a public address');
  const sitemap = sitemapXml('https://osrip.vercel.app');
  assert.equal(sitemap.match(/<loc>/g).length, PUBLIC_PAGES.length);
  for (const prefix of PRIVATE_PREFIXES) assert.ok(!sitemap.includes(`osrip.vercel.app${prefix}`), prefix);
});

test('the published interface is served with the same security headers as the prepared server', () => {
  const config = JSON.parse(readFileSync(new URL('../vercel.json', import.meta.url), 'utf8'));
  const all = Object.fromEntries(config.headers.find((h) => h.source === '/(.*)').headers.map((h) => [h.key, h.value]));
  assert.equal(all['X-Frame-Options'], 'DENY');
  assert.equal(all['X-Content-Type-Options'], 'nosniff');
  assert.match(all['Content-Security-Policy'], /frame-ancestors 'none'/);
  assert.match(all['Content-Security-Policy'], /default-src 'self'/);
  const caddy = readFileSync(new URL('../../deploy/Caddyfile', import.meta.url), 'utf8');
  assert.ok(caddy.includes(all['Content-Security-Policy']), 'the same policy as deploy/Caddyfile');
});

test('the page names itself OSRIP for people and search engines', () => {
  const html = readFileSync(new URL('../index.html', import.meta.url), 'utf8');
  assert.match(html, /<title>OSRIP – Oman Smart Resource Intelligence Platform<\/title>/);
  assert.match(html, /<meta property="og:site_name" content="OSRIP" \/>/);
  assert.match(html, /<meta name="description" content="OSRIP, the Oman Smart Resource Intelligence Platform/);
  assert.ok(!/localhost|127\.0\.0\.1/.test(html), 'no local address in the page');
});
