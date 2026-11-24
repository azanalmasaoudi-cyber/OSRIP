/**
 * The site's public address, only when one is really allocated: VITE_PUBLIC_SITE_URL, or on
 * Vercel's production build the domain Vercel assigned (VERCEL_PROJECT_PRODUCTION_URL). Never a
 * local address and never guessed: without one, the build writes no canonical link and no
 * sitemap (vite.config.ts). No runtime imports: tested with Node (tests/site-url.test.mjs).
 */
export function publicSiteUrl(env: Readonly<Record<string, string | undefined>>): string | null {
  const vercel = env.VERCEL_ENV === 'production' && env.VERCEL_PROJECT_PRODUCTION_URL ? `https://${env.VERCEL_PROJECT_PRODUCTION_URL}` : '';
  const raw = env.VITE_PUBLIC_SITE_URL || vercel;
  if (!raw) return null;
  let url: URL;
  try {
    url = new URL(raw);
  } catch {
    return null;
  }
  const local = ['localhost', '127.0.0.1', '[::1]'].includes(url.hostname) || url.hostname.endsWith('.localhost');
  if (url.protocol !== 'https:' || local) return null;
  return url.origin;
}

/** Public pages a search engine may list (sign-in, account and administration are left out). */
export const PUBLIC_PAGES = ['/', '/overview', '/energy/electricity', '/energy/water', '/food-security', '/trade', '/assistant',
  '/geography', '/datasets', '/library', '/sources', '/methodology'] as const;

/** Paths robots.txt asks search engines not to list (they are protected by sign-in anyway). */
export const PRIVATE_PREFIXES = ['/admin/', '/account', '/settings', '/data-management', '/sign-in', '/register', '/forgot-password',
  '/design-reference', '/api/'] as const;

export function robotsTxt(site: string | null): string {
  const lines = ['User-agent: *', 'Allow: /', ...PRIVATE_PREFIXES.map((p) => `Disallow: ${p}`)];
  if (site) lines.push('', `Sitemap: ${site}/sitemap.xml`);
  return `${lines.join('\n')}\n`;
}

export function sitemapXml(site: string): string {
  const urls = PUBLIC_PAGES.map((p) => `  <url><loc>${site}${p}</loc></url>`).join('\n');
  return `<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n${urls}\n</urlset>\n`;
}
