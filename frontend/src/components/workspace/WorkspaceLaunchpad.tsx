import { ArrowUpRight, AudioLines, BookOpen, FlaskConical, LineChart } from 'lucide-react';
import { Link } from 'react-router';
import { useTranslation } from 'react-i18next';

import { usePreservedSearch } from '@/state/usePreservedSearch';

const DESTINATIONS = [
  { path: '/talk', key: 'talk', icon: AudioLines },
  { path: '/studies', key: 'studies', icon: FlaskConical },
  { path: '/forecasts', key: 'scenarios', icon: LineChart },
  { path: '/sources', key: 'sources', icon: BookOpen },
] as const;

/** The workspace's next steps: talk to the assistant, studies, scenarios and sources. Links keep
 * the data mode and other query parameters, like the navigation. */
export function WorkspaceLaunchpad() {
  const { t } = useTranslation();
  const to = usePreservedSearch();
  return (
    <section className="mb-6 overflow-hidden rounded-2xl border border-primary/20 bg-card shadow-sm" aria-label={t('workspace.launchpad.label')}
      data-testid="workspace-launchpad">
      <div className="border-b border-primary/15 bg-primary/5 px-5 py-4">
        <p className="text-xs font-semibold tracking-wide text-primary uppercase">{t('app.shortName')} / {t('workspace.launchpad.eyebrow')}</p>
        <h2 className="mt-2 text-xl font-semibold">{t('workspace.launchpad.title')}</h2>
        <p className="mt-1 text-sm text-muted-foreground">{t('workspace.launchpad.intro')}</p>
      </div>
      <div className="grid gap-px bg-border sm:grid-cols-2 xl:grid-cols-4">
        {DESTINATIONS.map(({ path, key, icon: Icon }) => (
          <Link key={path} to={to(path)} data-testid={`launchpad-${key}`}
            className="group flex min-h-32 flex-col gap-2 bg-card p-4 transition-colors hover:bg-muted focus-visible:outline-2 focus-visible:outline-primary focus-visible:outline-offset-[-3px]">
            <span className="flex items-center justify-between text-primary">
              <Icon size={22} aria-hidden="true" /><ArrowUpRight size={16} aria-hidden="true" className="rtl:-scale-x-100" />
            </span>
            <span className="text-sm font-semibold">{t(`workspace.launchpad.${key}.title`)}</span>
            <span className="text-xs leading-relaxed text-muted-foreground">{t(`workspace.launchpad.${key}.note`)}</span>
          </Link>
        ))}
      </div>
    </section>
  );
}
