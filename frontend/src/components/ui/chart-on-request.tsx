import { BarChart3, EyeOff } from 'lucide-react';
import { useId, useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

/**
 * A chart that is never drawn unasked: a "Show chart" button, and the chart (from the same rows
 * as the table next to it) only after it is pressed. "Hide chart" removes it again. The chart's
 * children are not rendered while it is closed, so nothing is measured or animated meanwhile.
 */
export function ChartOnRequest({ children, label, className, testId = 'chart-toggle', defaultOpen = false }: {
  children: ReactNode;
  /** What the chart shows, for the button's accessible name ("Show chart: Water production"). */
  label?: string;
  className?: string;
  testId?: string;
  /** True only when the person asked for this chart in words (e.g. "show a chart of ..."). */
  defaultOpen?: boolean;
}) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(defaultOpen);
  const id = useId();
  return (
    <div className={cn('flex flex-col gap-3', className)} data-testid={testId} data-open={open ? 'true' : 'false'}>
      <Button type="button" variant="outline" size="sm" className="w-fit" aria-expanded={open} aria-controls={id}
        onClick={() => setOpen(!open)} data-testid={open ? `${testId}-hide` : `${testId}-show`}>
        {open ? <EyeOff aria-hidden="true" /> : <BarChart3 aria-hidden="true" />}
        {open ? t('chart.hide') : t('chart.show')}
        {label ? <span className="sr-only">: {label}</span> : null}
      </Button>
      <div id={id} hidden={!open}>{open ? children : null}</div>
    </div>
  );
}
