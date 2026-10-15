import type { ReactNode } from 'react';

import { LatticeBackdrop } from '@/components/brand/BrandMark';
import { SectorIllustration, type Sector } from '@/components/brand/SectorIllustration';
import { useDocumentTitle } from '@/lib/useDocumentTitle';

interface PageHeaderProps {
  title: string;
  intro?: string;
  /** Small label above the title, e.g. the parent domain. */
  eyebrow?: string;
  /** Set to false in layouts whose child views set the document title themselves. */
  setsDocumentTitle?: boolean;
  /** Sector illustration shown beside the title from the small-tablet width up. */
  illustration?: Sector;
  children?: ReactNode;
}

function DocumentTitle({ title }: { title: string }) {
  useDocumentTitle(title);
  return null;
}

export function PageHeader({ title, intro, eyebrow, setsDocumentTitle = true, illustration, children }: PageHeaderProps) {
  return (
    <header className="surface-card relative mb-8 overflow-hidden px-5 py-6 sm:px-8 sm:py-8">
      {setsDocumentTitle ? <DocumentTitle title={title} /> : null}
      <LatticeBackdrop className="bg-sand/15" />
      <div aria-hidden="true" className="absolute inset-y-0 start-0 w-1 bg-gradient-to-b from-copper via-copper/70 to-sand" />
      <div className="relative grid items-center gap-6 sm:grid-cols-[minmax(0,1fr)_auto]">
        <div className="flex min-w-0 flex-col gap-2">
          {/* Letter-spacing is LTR-only: it breaks the joining of Arabic letters. */}
          {eyebrow ? <p className="text-xs font-semibold text-sand-foreground ltr:tracking-wide ltr:uppercase">{eyebrow}</p> : null}
          <h1 className="text-2xl font-semibold ltr:tracking-tight sm:text-3xl">{title}</h1>
          {intro ? <p className="max-w-3xl text-sm text-muted-foreground sm:text-base">{intro}</p> : null}
          {children}
        </div>
        {illustration ? <SectorIllustration sector={illustration} className="hidden w-48 sm:block lg:w-64" eager /> : null}
      </div>
    </header>
  );
}
