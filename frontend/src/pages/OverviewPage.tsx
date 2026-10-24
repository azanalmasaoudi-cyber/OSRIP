import {
  ArrowRight,
  BarChart3,
  BookOpen,
  CalendarRange,
  Droplets,
  GraduationCap,
  LayoutDashboard,
  MessageSquareText,
  MousePointerClick,
  Ship,
  Wheat,
  Zap,
  type LucideIcon,
} from 'lucide-react';
import { Link } from 'react-router';
import { useTranslation } from 'react-i18next';

import { PageHeader } from '@/components/common/PageHeader';
import { Badge } from '@/components/ui/badge';
import { buttonVariants } from '@/components/ui/button';
import { usePreservedSearch } from '@/state/usePreservedSearch';

const SECTORS: readonly { key: 'electricity' | 'water' | 'food' | 'trade'; path: string; icon: LucideIcon }[] = [
  { key: 'electricity', path: '/energy/electricity', icon: Zap },
  { key: 'water', path: '/energy/water', icon: Droplets },
  { key: 'food', path: '/food-security', icon: Wheat },
  { key: 'trade', path: '/trade', icon: Ship },
];

const STEPS: readonly { key: 'sector' | 'period' | 'results' | 'analysis'; icon: LucideIcon }[] = [
  { key: 'sector', icon: MousePointerClick },
  { key: 'period', icon: CalendarRange },
  { key: 'results', icon: BarChart3 },
  { key: 'analysis', icon: MessageSquareText },
];

/**
 * The project introduction: what OSRIP is (an academic decision-support project, not an
 * official government service), the problem it addresses, its goal, the four sectors and
 * what each covers, how to use it, and where the data come from, how they are updated and
 * what they cannot tell. It draws no charts and shows no statistics by itself; the cards
 * lead to the sectors, where results appear only after a period is chosen.
 */
export function OverviewPage() {
  const { t } = useTranslation();
  const to = usePreservedSearch();

  return (
    <div className="flex flex-col gap-8" data-testid="overview-intro">
      <PageHeader title={t('overviewIntro.title')} intro={t('overviewIntro.lead')} eyebrow={t('overviewIntro.eyebrow')}>
        <p className="flex flex-wrap items-center gap-2 text-xs" data-testid="overview-status">
          <Badge variant="sand"><GraduationCap aria-hidden="true" className="me-1 size-3.5" />{t('overviewIntro.academic')}</Badge>
          <span className="text-muted-foreground">{t('overviewIntro.notOfficial')}</span>
        </p>
      </PageHeader>

      <div className="grid gap-4 md:grid-cols-2">
        <section aria-labelledby="ov-problem" className="surface-card flex flex-col gap-2 p-5" data-testid="overview-problem">
          <h2 id="ov-problem" className="text-base font-semibold">{t('overviewIntro.problemHeading')}</h2>
          <p className="text-sm text-muted-foreground">{t('overviewIntro.problem')}</p>
        </section>
        <section aria-labelledby="ov-goal" className="surface-card flex flex-col gap-2 p-5" data-testid="overview-goal">
          <h2 id="ov-goal" className="text-base font-semibold">{t('overviewIntro.goalHeading')}</h2>
          <p className="text-sm text-muted-foreground">{t('overviewIntro.goal')}</p>
        </section>
      </div>

      <section aria-labelledby="ov-sectors" className="flex flex-col gap-3">
        <h2 id="ov-sectors" className="text-lg font-semibold">{t('overviewIntro.sectorsHeading')}</h2>
        <ul className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {SECTORS.map((s) => {
            const Icon = s.icon;
            return (
              <li key={s.key} className="surface-card flex flex-col gap-3 p-5" data-testid="overview-sector" data-sector={s.key}>
                <h3 className="flex items-center gap-2 text-base font-semibold">
                  <Icon aria-hidden="true" className="size-5 text-primary" />{t(`pages.${s.key}.title`)}
                </h3>
                <p className="flex-1 text-sm text-muted-foreground">{t(`overviewIntro.sectors.${s.key}`)}</p>
                <Link to={to(s.path)} className={buttonVariants({ variant: 'outline', size: 'sm' })} data-testid="overview-sector-link">
                  {t('overviewIntro.openSector', { name: t(`pages.${s.key}.title`) })}
                  <ArrowRight aria-hidden="true" className="rtl:rotate-180" />
                </Link>
              </li>
            );
          })}
        </ul>
      </section>

      <section aria-labelledby="ov-how" className="flex flex-col gap-3">
        <h2 id="ov-how" className="text-lg font-semibold">{t('overviewIntro.howHeading')}</h2>
        <ol className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4" data-testid="overview-steps">
          {STEPS.map((step, i) => {
            const Icon = step.icon;
            return (
              <li key={step.key} className="flex gap-3 rounded-lg border border-border bg-card p-4">
                <span aria-hidden="true" className="flex size-8 shrink-0 items-center justify-center rounded-full bg-primary/10 text-sm font-semibold text-primary">
                  {i + 1}
                </span>
                <div className="flex flex-col gap-1">
                  <p className="flex items-center gap-1.5 text-sm font-semibold"><Icon aria-hidden="true" className="size-4" />{t(`overviewIntro.steps.${step.key}.title`)}</p>
                  <p className="text-xs text-muted-foreground">{t(`overviewIntro.steps.${step.key}.body`)}</p>
                </div>
              </li>
            );
          })}
        </ol>
      </section>

      <section aria-labelledby="ov-data" className="grid gap-4 lg:grid-cols-3" data-testid="overview-data">
        <h2 id="ov-data" className="text-lg font-semibold lg:col-span-3">{t('overviewIntro.dataHeading')}</h2>
        <div className="surface-card flex flex-col gap-2 p-5">
          <h3 className="text-sm font-semibold">{t('overviewIntro.sourcesHeading')}</h3>
          <p className="text-sm text-muted-foreground">{t('overviewIntro.sources')}</p>
        </div>
        <div className="surface-card flex flex-col gap-2 p-5">
          <h3 className="text-sm font-semibold">{t('overviewIntro.updatesHeading')}</h3>
          <p className="text-sm text-muted-foreground">{t('overviewIntro.updates')}</p>
        </div>
        <div className="surface-card flex flex-col gap-2 p-5">
          <h3 className="text-sm font-semibold">{t('overviewIntro.limitsHeading')}</h3>
          <ul className="flex list-disc flex-col gap-1 ps-4 text-sm text-muted-foreground">
            {(['coverage', 'missing', 'frequency', 'ai', 'official'] as const).map((k) => (
              <li key={k}>{t(`overviewIntro.limits.${k}`)}</li>
            ))}
          </ul>
        </div>
      </section>

      <div className="flex flex-wrap gap-2">
        <Link to={to('/sources')} className={buttonVariants({ variant: 'outline' })}>
          <BookOpen aria-hidden="true" />{t('overviewIntro.sourcesLink')}
        </Link>
        <Link to={to('/workspace')} className={buttonVariants({ variant: 'outline' })}>
          <LayoutDashboard aria-hidden="true" />{t('overviewIntro.workspaceLink')}
        </Link>
      </div>
    </div>
  );
}
