import {
  ArrowRight,
  BarChart3,
  BookOpen,
  Bot,
  Building2,
  CalendarRange,
  CheckCircle2,
  ClipboardList,
  FileSearch,
  FileText,
  FlaskConical,
  GraduationCap,
  Landmark,
  Languages,
  LayoutDashboard,
  ListChecks,
  MapPin,
  MessageSquareText,
  MousePointerClick,
  Newspaper,
  Save,
  Scale,
  Search,
  ShieldCheck,
  Table2,
  Target,
  TrendingUp,
  type LucideIcon,
} from 'lucide-react';
import { Link } from 'react-router';
import { useTranslation } from 'react-i18next';

import type { Sector } from '@/components/brand/SectorIllustration';
import { SectorImage } from '@/components/brand/SectorImage';
import { PhotoCaption } from '@/components/common/Photo';
import { QualityLegend } from '@/components/common/QualityBadges';
import { Badge } from '@/components/ui/badge';
import { buttonVariants } from '@/components/ui/button';
import { PHOTOS } from '@/content/photos';
import { useAppLanguage } from '@/lib/useAppLanguage';
import { useDocumentTitle } from '@/lib/useDocumentTitle';
import { cn } from '@/lib/utils';
import { usePreservedSearch } from '@/state/usePreservedSearch';

const SECTORS: readonly { key: 'electricity' | 'water' | 'food' | 'trade'; image: Sector; path: string }[] = [
  { key: 'electricity', image: 'electricity', path: '/energy/electricity' },
  { key: 'water', image: 'water', path: '/energy/water' },
  { key: 'food', image: 'food', path: '/food-security' },
  { key: 'trade', image: 'trade', path: '/trade' },
];

/** The sector page's flow, in order. */
const STEPS: readonly { key: 'sector' | 'indicator' | 'area' | 'period' | 'results' | 'chart'; icon: LucideIcon }[] = [
  { key: 'sector', icon: MousePointerClick },
  { key: 'indicator', icon: ListChecks },
  { key: 'area', icon: MapPin },
  { key: 'period', icon: CalendarRange },
  { key: 'results', icon: Table2 },
  { key: 'chart', icon: BarChart3 },
];

/** The assistant's conversation, in order. */
const AI_STEPS: readonly { key: 'ask' | 'research' | 'read' | 'verify' | 'table' | 'chart' | 'report'; icon: LucideIcon }[] = [
  { key: 'ask', icon: MessageSquareText },
  { key: 'research', icon: Search },
  { key: 'read', icon: FileSearch },
  { key: 'verify', icon: ShieldCheck },
  { key: 'table', icon: Table2 },
  { key: 'chart', icon: BarChart3 },
  { key: 'report', icon: Save },
];

const USERS: readonly { key: 'policy' | 'analysts' | 'research' | 'public'; icon: LucideIcon }[] = [
  { key: 'policy', icon: Landmark },
  { key: 'analysts', icon: Scale },
  { key: 'research', icon: GraduationCap },
  { key: 'public', icon: Newspaper },
];

const OFFICIAL = ['ncsi', 'ministries', 'regulators', 'companies', 'portals'] as const;

const BENEFITS: readonly { key: 'access' | 'consistency' | 'evidence' | 'bilingual'; icon: LucideIcon }[] = [
  { key: 'access', icon: TrendingUp },
  { key: 'consistency', icon: CheckCircle2 },
  { key: 'evidence', icon: ClipboardList },
  { key: 'bilingual', icon: Languages },
];

function SectionHeading({ id, children }: { id: string; children: string }) {
  return <h2 id={id} className="gold-rule text-xl font-semibold sm:text-2xl">{children}</h2>;
}

/**
 * The project introduction: what OSRIP is for (an academic decision-support project, not an
 * official government service), the problem, who it is for, the four sectors, how a sector
 * page works, what the AI Assistant does and does not do, how reliable the data are, and the
 * expected benefits. It draws no charts and shows no statistics by itself; the cards lead to
 * the sectors, where results appear only after a period is chosen.
 */
export function OverviewPage() {
  const { t } = useTranslation();
  const language = useAppLanguage();
  const to = usePreservedSearch();
  useDocumentTitle(t('overviewIntro.title'));
  const hero = PHOTOS.bahla;

  return (
    <div className="flex flex-col gap-10 lg:gap-14" data-testid="overview-intro">
      {/* Purpose: a navy band beside a credited photograph of a real place. */}
      <section aria-labelledby="ov-title" className="on-nav overflow-hidden rounded-xl bg-nav text-nav-foreground shadow-raised">
        <div className="grid lg:grid-cols-[minmax(0,1.1fr)_minmax(0,0.9fr)]">
          <div className="flex flex-col gap-5 p-6 sm:p-8 lg:p-10 3xl:p-14">
            <p className="text-sm font-semibold text-nav-ring ltr:tracking-wider ltr:uppercase">{t('overviewIntro.eyebrow')}</p>
            <h1 id="ov-title" className="max-w-3xl text-3xl leading-tight font-semibold sm:text-4xl 3xl:text-5xl">{t('overviewIntro.title')}</h1>
            <p className="max-w-2xl text-base text-nav-muted sm:text-lg">{t('overviewIntro.lead')}</p>
            <p className="flex flex-wrap items-center gap-2 text-base" data-testid="overview-status">
              <Badge variant="sand"><GraduationCap aria-hidden="true" />{t('overviewIntro.academic')}</Badge>
              <span className="text-nav-muted">{t('overviewIntro.notOfficial')}</span>
            </p>
            <div className="flex flex-wrap gap-3 pt-1">
              <Link to={to('/energy/electricity')} className={buttonVariants({ size: 'lg' })} data-testid="overview-cta-sector">
                {t('overviewIntro.ctaSector')}<ArrowRight aria-hidden="true" className="rtl:-scale-x-100" />
              </Link>
              <Link to={to('/assistant')} data-testid="overview-cta-assistant"
                className={cn(buttonVariants({ size: 'lg', variant: 'outline' }), 'border-nav-foreground/40 bg-transparent text-nav-foreground hover:bg-nav-active')}>
                <Bot aria-hidden="true" />{t('overviewIntro.ctaAssistant')}
              </Link>
            </div>
          </div>
          <figure className="relative m-0 min-h-56 lg:min-h-full" data-testid="photo">
            <img src={hero.src} width={hero.width} height={hero.height} alt={hero.alt[language]} sizes="(min-width: 1024px) 45vw, 100vw"
              className="absolute inset-0 size-full object-cover" decoding="async" />
            <PhotoCaption photo={hero}
              className="absolute end-0 bottom-0 max-w-full rounded-ss-md bg-black/65 px-2.5 py-1 text-xs text-white [&_a]:text-white" />
          </figure>
        </div>
      </section>

      {/* The problem and the purpose */}
      <div className="grid gap-4 md:grid-cols-2">
        <section aria-labelledby="ov-problem" className="surface-card flex flex-col gap-2 p-6" data-testid="overview-problem">
          <h2 id="ov-problem" className="flex items-center gap-2 text-lg font-semibold">
            <FileSearch aria-hidden="true" className="size-5 text-copper" />{t('overviewIntro.problemHeading')}
          </h2>
          <p className="text-base text-muted-foreground">{t('overviewIntro.problem')}</p>
        </section>
        <section aria-labelledby="ov-goal" className="surface-card flex flex-col gap-2 p-6" data-testid="overview-goal">
          <h2 id="ov-goal" className="flex items-center gap-2 text-lg font-semibold">
            <Target aria-hidden="true" className="size-5 text-primary" />{t('overviewIntro.goalHeading')}
          </h2>
          <p className="text-base text-muted-foreground">{t('overviewIntro.goal')}</p>
        </section>
      </div>

      {/* Who it is for */}
      <section aria-labelledby="ov-users" className="flex flex-col gap-4" data-testid="overview-users">
        <SectionHeading id="ov-users">{t('overviewIntro.usersHeading')}</SectionHeading>
        <ul className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {USERS.map(({ key, icon: Icon }) => (
            <li key={key} className="surface-card flex flex-col gap-2 p-5">
              <span className="flex size-10 items-center justify-center rounded-lg bg-muted text-foreground"><Icon aria-hidden="true" className="size-5" /></span>
              <h3 className="text-base font-semibold">{t(`overviewIntro.users.${key}.title`)}</h3>
              <p className="text-base text-muted-foreground">{t(`overviewIntro.users.${key}.body`)}</p>
            </li>
          ))}
        </ul>
      </section>

      {/* The four sectors */}
      <section aria-labelledby="ov-sectors" className="flex flex-col gap-4">
        <SectionHeading id="ov-sectors">{t('overviewIntro.sectorsHeading')}</SectionHeading>
        <ul className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {SECTORS.map((s) => (
            <li key={s.key} className="surface-card card-link flex flex-col overflow-hidden" data-testid="overview-sector" data-sector={s.key}>
              <SectorImage sector={s.image} />
              <div className="flex flex-1 flex-col gap-3 p-5">
                <h3 className="text-lg font-semibold">{t(`pages.${s.key}.title`)}</h3>
                <p className="flex-1 text-base text-muted-foreground">{t(`overviewIntro.sectors.${s.key}`)}</p>
                <Link to={to(s.path)} className={cn(buttonVariants({ variant: 'outline', size: 'sm' }), 'w-fit')} data-testid="overview-sector-link">
                  {t('overviewIntro.openSector', { name: t(`pages.${s.key}.title`) })}
                  <ArrowRight aria-hidden="true" className="rtl:rotate-180" />
                </Link>
              </div>
            </li>
          ))}
        </ul>
      </section>

      {/* How a sector page works */}
      <section aria-labelledby="ov-how" className="flex flex-col gap-4">
        <SectionHeading id="ov-how">{t('overviewIntro.howHeading')}</SectionHeading>
        <ol className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-6" data-testid="overview-steps">
          {STEPS.map((step, i) => {
            const Icon = step.icon;
            return (
              <li key={step.key} className="flex gap-3 rounded-lg border border-border bg-card p-4 shadow-card">
                <span aria-hidden="true" className="flex size-8 shrink-0 items-center justify-center rounded-full bg-foreground text-sm font-semibold text-background">
                  {i + 1}
                </span>
                <div className="flex min-w-0 flex-col gap-1">
                  <p className="flex items-center gap-1.5 text-base font-semibold"><Icon aria-hidden="true" className="size-4 text-primary" />{t(`overviewIntro.steps.${step.key}.title`)}</p>
                  <p className="text-base text-muted-foreground">{t(`overviewIntro.steps.${step.key}.body`)}</p>
                </div>
              </li>
            );
          })}
        </ol>
      </section>

      {/* The AI Assistant's role */}
      <section aria-labelledby="ov-ai" className="grid gap-6 rounded-xl border border-border bg-card p-6 shadow-card sm:p-8 xl:grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)]"
        data-testid="overview-ai">
        <div className="flex flex-col gap-4">
          <SectionHeading id="ov-ai">{t('overviewIntro.aiHeading')}</SectionHeading>
          <p className="max-w-2xl text-base text-muted-foreground">{t('overviewIntro.aiLead')}</p>
          <ol className="grid gap-3 sm:grid-cols-2" data-testid="overview-ai-steps">
            {AI_STEPS.map(({ key, icon: Icon }, i) => (
              <li key={key} className="flex items-start gap-2.5 text-base">
                <span aria-hidden="true" className="mt-0.5 flex size-6 shrink-0 items-center justify-center rounded-full border border-copper text-xs font-semibold text-accent">{i + 1}</span>
                <span className="flex min-w-0 flex-col">
                  <span className="flex items-center gap-1.5 font-semibold"><Icon aria-hidden="true" className="size-4 text-primary" />{t(`overviewIntro.aiSteps.${key}.title`)}</span>
                  <span className="text-base text-muted-foreground">{t(`overviewIntro.aiSteps.${key}.body`)}</span>
                </span>
              </li>
            ))}
          </ol>
          <Link to={to('/assistant')} className={cn(buttonVariants(), 'w-fit')}>
            <Bot aria-hidden="true" />{t('overviewIntro.ctaAssistant')}
          </Link>
        </div>
        <div className="flex flex-col gap-3 rounded-lg border border-border bg-muted/60 p-5">
          <h3 className="text-base font-semibold">{t('overviewIntro.aiRulesHeading')}</h3>
          <ul className="flex list-disc flex-col gap-2 ps-5 text-base text-muted-foreground">
            {(['noInvent', 'missing', 'unreviewed', 'web', 'optional'] as const).map((k) => (
              <li key={k}>{t(`overviewIntro.aiRules.${k}`)}</li>
            ))}
          </ul>
        </div>
      </section>

      {/* Data reliability */}
      <section aria-labelledby="ov-data" className="flex flex-col gap-5" data-testid="overview-data">
        <SectionHeading id="ov-data">{t('overviewIntro.dataHeading')}</SectionHeading>
        <div className="grid gap-4 xl:grid-cols-3">
          <div className="surface-card flex flex-col gap-3 p-5" data-testid="overview-official-first">
            <h3 className="flex items-center gap-2 text-base font-semibold"><Building2 aria-hidden="true" className="size-5 text-primary" />{t('overviewIntro.officialHeading')}</h3>
            <p className="text-base text-muted-foreground">{t('overviewIntro.officialLead')}</p>
            <ol className="flex flex-col gap-1.5 text-base">
              {OFFICIAL.map((k, i) => (
                <li key={k} className="flex items-baseline gap-2">
                  <span aria-hidden="true" className="w-4 shrink-0 text-xs font-semibold text-accent tabular-nums">{i + 1}</span>
                  <span>{t(`overviewIntro.official.${k}`)}</span>
                </li>
              ))}
            </ol>
          </div>
          <div className="surface-card flex flex-col gap-2 p-5">
            <h3 className="text-base font-semibold">{t('overviewIntro.updatesHeading')}</h3>
            <p className="text-base text-muted-foreground">{t('overviewIntro.updates')}</p>
            <h3 className="mt-2 text-base font-semibold">{t('overviewIntro.sourcesHeading')}</h3>
            <p className="text-base text-muted-foreground">{t('overviewIntro.sources')}</p>
          </div>
          <div className="surface-card flex flex-col gap-2 p-5">
            <h3 className="text-base font-semibold">{t('overviewIntro.limitsHeading')}</h3>
            <ul className="flex list-disc flex-col gap-1 ps-4 text-base text-muted-foreground">
              {(['coverage', 'missing', 'frequency', 'ai', 'official'] as const).map((k) => (
                <li key={k}>{t(`overviewIntro.limits.${k}`)}</li>
              ))}
            </ul>
          </div>
        </div>
        <div className="flex flex-col gap-3">
          <h3 className="text-base font-semibold">{t('overviewIntro.qualityHeading')}</h3>
          <QualityLegend />
        </div>
      </section>

      {/* Expected benefits */}
      <section aria-labelledby="ov-benefits" className="flex flex-col gap-4" data-testid="overview-benefits">
        <SectionHeading id="ov-benefits">{t('overviewIntro.benefitsHeading')}</SectionHeading>
        <ul className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {BENEFITS.map(({ key, icon: Icon }) => (
            <li key={key} className="surface-card flex gap-3 p-5">
              <Icon aria-hidden="true" className="mt-0.5 size-5 shrink-0 text-primary" />
              <div className="flex flex-col gap-1">
                <h3 className="text-base font-semibold">{t(`overviewIntro.benefits.${key}.title`)}</h3>
                <p className="text-base text-muted-foreground">{t(`overviewIntro.benefits.${key}.body`)}</p>
              </div>
            </li>
          ))}
        </ul>
      </section>

      <div className="flex flex-wrap gap-2">
        <Link to={to('/sources')} className={buttonVariants({ variant: 'outline' })}>
          <BookOpen aria-hidden="true" />{t('overviewIntro.sourcesLink')}
        </Link>
        <Link to={to('/studies')} className={buttonVariants({ variant: 'outline' })}>
          <FlaskConical aria-hidden="true" />{t('nav.studies')}
        </Link>
        <Link to={to('/reports')} className={buttonVariants({ variant: 'outline' })}>
          <FileText aria-hidden="true" />{t('nav.reports')}
        </Link>
        <Link to={to('/workspace')} className={buttonVariants({ variant: 'outline' })}>
          <LayoutDashboard aria-hidden="true" />{t('overviewIntro.workspaceLink')}
        </Link>
      </div>
    </div>
  );
}
