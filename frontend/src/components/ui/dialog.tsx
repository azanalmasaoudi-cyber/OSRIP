import { X } from 'lucide-react';
import { useEffect, useId, useRef, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

import { cn } from '@/lib/utils';

interface DialogProps {
  open: boolean;
  onClose: () => void;
  title: string;
  description?: string;
  children: ReactNode;
  /** `center` for content dialogs, `start` for the navigation drawer (follows text direction). */
  placement?: 'center' | 'start' | 'end';
  className?: string;
}

/**
 * Native <dialog> shown with showModal(): the browser makes the rest of the
 * page inert, keeps focus inside, closes on Escape and restores focus to the
 * opener. No focus-trap library is needed.
 */
export function Dialog({ open, onClose, title, description, children, placement = 'center', className }: DialogProps) {
  const { t } = useTranslation();
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  const descriptionId = useId();

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);

  return (
    // The click handler only closes on a backdrop click; the keyboard equivalent is Escape (onCancel).
    // eslint-disable-next-line jsx-a11y/click-events-have-key-events, jsx-a11y/no-noninteractive-element-interactions
    <dialog
      ref={ref}
      aria-labelledby={titleId}
      aria-describedby={description ? descriptionId : undefined}
      onClose={onClose}
      onCancel={(event) => {
        event.preventDefault();
        onClose();
      }}
      onClick={(event) => {
        // A click on the backdrop lands on the <dialog> element itself.
        if (event.target === event.currentTarget) onClose();
      }}
      className={cn(
        'bg-card text-card-foreground',
        placement === 'end' && 'open:flex open:flex-col',
        placement === 'center' &&
          'm-auto w-[min(40rem,calc(100vw-2rem))] max-h-[calc(100dvh-2rem)] rounded-lg border border-border p-0 shadow-raised',
        placement === 'start' &&
          'm-0 me-auto h-dvh max-h-dvh w-[min(18rem,85vw)] max-w-none border-e border-sidebar-border bg-sidebar p-0 text-sidebar-foreground',
        placement === 'end' && 'm-0 ms-auto h-dvh max-h-dvh w-[min(32rem,100vw)] max-w-none border-s border-border p-0',
        className,
      )}
    >
      <div className="flex items-start justify-between gap-4 border-b border-current/15 px-5 py-4">
        <div className="flex flex-col gap-1">
          <h2 id={titleId} className="text-lg font-semibold leading-snug">
            {title}
          </h2>
          {description ? (
            <p id={descriptionId} className="text-sm opacity-80">
              {description}
            </p>
          ) : null}
        </div>
        <button
          type="button"
          onClick={onClose}
          className="-me-2 inline-flex size-10 shrink-0 items-center justify-center rounded-md hover:bg-current/10"
        >
          <X aria-hidden="true" className="size-5" />
          <span className="sr-only">{t('dialog.close')}</span>
        </button>
      </div>
      <div className={placement === 'end' ? 'flex min-h-0 flex-1 flex-col' : 'px-5 py-4'}>{children}</div>
    </dialog>
  );
}
