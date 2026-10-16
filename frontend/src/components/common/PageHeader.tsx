import type { ReactNode } from 'react';

import { SectorIllustration, type Sector } from '@/components/brand/SectorIllustration';
import { useDocumentTitle } from '@/lib/useDocumentTitle';

interface PageHeaderProps {
  title: string;
  intro?: string;
  /** Small label above the title, e.g. the parent domain. */
  eyebrow?: string;
  /** Set to false in layouts whose child views set the document title themselves. */
  setsDocumentTitle?: boolean;
  /** Sector illustration beside the title from the tablet width up. */
  illustration?: Sector;
  children?: ReactNode;
}

function DocumentTitle({ title }: { title: string }) {
  useDocumentTitle(title);
  return null;
}

/** The page's heading: compact, above the page's cards (the top bar names the section). */
export function PageHeader({ title, intro, eyebrow, setsDocumentTitle = true, illustration, children }: PageHeaderProps) {
  return (
    <header className="mb-6 grid items-center gap-4 sm:grid-cols-[minmax(0,1fr)_auto]">
      {setsDocumentTitle ? <DocumentTitle title={title} /> : null}
      <div className="flex min-w-0 flex-col gap-1.5">
        {/* Letter-spacing is LTR-only: it breaks the joining of Arabic letters. */}
        {eyebrow ? <p className="text-xs font-medium text-primary ltr:tracking-wider ltr:uppercase">{eyebrow}</p> : null}
        <h1 className="text-xl font-semibold ltr:tracking-tight sm:text-2xl">{title}</h1>
        {intro ? <p className="max-w-3xl text-sm text-muted-foreground">{intro}</p> : null}
        {children}
      </div>
      {illustration ? <SectorIllustration sector={illustration} className="hidden w-32 border border-border md:block lg:w-40" eager /> : null}
    </header>
  );
}
