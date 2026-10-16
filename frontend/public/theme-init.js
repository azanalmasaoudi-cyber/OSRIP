// Applies the remembered theme before the first paint, so a dark page never flashes white.
// Loaded synchronously from index.html as a file (the Content-Security-Policy forbids inline
// scripts); src/lib/theme.ts takes over once the app runs. Keep the key and default in step.
(() => {
  let preference = 'dark';
  try {
    const stored = window.localStorage.getItem('osrip.theme');
    if (stored === 'light' || stored === 'dark' || stored === 'system') preference = stored;
  } catch {
    // Storage blocked: the default.
  }
  const dark = preference === 'dark'
    || (preference === 'system' && window.matchMedia('(prefers-color-scheme: dark)').matches);
  document.documentElement.setAttribute('data-theme', dark ? 'dark' : 'light');
})();
