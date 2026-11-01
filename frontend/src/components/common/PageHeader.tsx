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

/** The page's heading: a large title with a short soft-gold rule, and at most one line of
 * introduction (the top bar names the section; explanations live on the Overview and Sources). */
export function PageHeader({ title, intro, eyebrow, setsDocumentTitle = true, illustration, children }: PageHeaderProps) {
  return (
    <header className="mb-6 grid items-center gap-4 sm:grid-cols-[minmax(0,1fr)_auto] lg:mb-8">
      {setsDocumentTitle ? <DocumentTitle title={title} /> : null}
      <div className="gold-rule flex min-w-0 flex-col gap-2">
        {/* Letter-spacing is LTR-only: it breaks the joining of Arabic letters. */}
        {eyebrow ? <p className="text-xs font-semibold text-primary ltr:tracking-wider ltr:uppercase">{eyebrow}</p> : null}
        <h1 className="text-2xl leading-tight font-semibold ltr:tracking-tight sm:text-3xl">{title}</h1>
        {intro ? <p className="max-w-3xl text-base text-muted-foreground">{intro}</p> : null}
        {children}
      </div>
      {illustration ? <SectorIllustration sector={illustration} className="hidden w-32 border border-border md:block lg:w-40" eager /> : null}
    </header>
  );
}
