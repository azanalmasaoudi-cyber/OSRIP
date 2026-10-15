import { Activity, CircleDashed, Eye, FlaskConical } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import type { BackendStatus } from '@/api/backendStatus';
import { LatticeBackdrop } from '@/components/brand/BrandMark';
import { useDocumentTitle } from '@/lib/useDocumentTitle';
import { cn } from '@/lib/utils';

const STATUS_ICON = { online: Activity, offline: Eye, checking: CircleDashed, mock: FlaskConical } as const;

export function DashboardHero({ status }: { status: BackendStatus }) {
  const { t } = useTranslation();
  const title = t('workspace.title');
  useDocumentTitle(title);
  const Icon = STATUS_ICON[status];

  return (
    <header className="relative overflow-hidden rounded-lg bg-nav px-5 py-7 text-nav-foreground shadow-raised sm:px-8 sm:py-9">
      <LatticeBackdrop className="opacity-40" />
      <div aria-hidden="true" className="absolute inset-x-0 top-0 h-1 bg-gradient-to-r from-copper via-sand to-copper" />
      <div className="relative flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between">
        <div className="flex max-w-3xl min-w-0 flex-col gap-2">
          {/* Letter-spacing is LTR-only: it breaks the joining of Arabic letters. */}
          <p className="text-xs font-semibold text-nav-ring ltr:tracking-widest ltr:uppercase">{t('dashboard.eyebrow')}</p>
          <h1 className="text-pretty text-2xl font-semibold ltr:tracking-tight sm:text-3xl lg:text-4xl">{title}</h1>
          <p className="text-pretty text-sm leading-relaxed text-nav-muted sm:text-base">{t('workspace.intro')}</p>
        </div>
        <p data-testid="backend-status" data-status={status}
          className={cn(
            'inline-flex w-fit shrink-0 items-center gap-2 rounded-full border px-3 py-1.5 text-sm font-medium',
            status === 'online' && 'border-nav-accent/50 bg-nav-accent/10 text-nav-foreground',
            status === 'offline' && 'border-copper bg-copper/20 text-nav-foreground',
            (status === 'checking' || status === 'mock') && 'border-nav-muted/40 text-nav-muted',
          )}>
          <Icon aria-hidden="true" className={cn('size-4', status === 'online' && 'text-nav-accent', status === 'checking' && 'motion-safe:animate-spin')} />
          {t(`dashboard.status.${status}`)}
        </p>
      </div>
    </header>
  );
}
