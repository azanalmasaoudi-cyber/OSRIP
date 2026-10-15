import { BookOpenText, Brain, ExternalLink, Trash2 } from 'lucide-react';
import { useState } from 'react';
import { Link } from 'react-router';
import { useTranslation } from 'react-i18next';

import {
  useAssistantProfile,
  useDeleteAllConversations,
  useDeleteGuestConversation,
  useMemory,
} from '@/api/assistant';
import { usePersona } from '@/components/assistant/persona';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { formatPeriod } from '@/lib/format';
import { useAppLanguage } from '@/lib/useAppLanguage';
import { usePreservedSearch } from '@/state/usePreservedSearch';

/** The chosen persona's approved profile: name, meaning (with the interpretation labelled as
 * such), the dictionary reference as cited in the booklet (Al Mulhim), and the capabilities
 * and limits shared by both personas. Read-only. */
export function AboutMulhim() {
  const { t } = useTranslation();
  const language = useAppLanguage();
  const [open, setOpen] = useState(false);
  const profile = useAssistantProfile();
  const { persona: chosen } = usePersona();
  const p = profile.data;
  const who = p?.personas.find((x) => x.code === chosen.code);
  const name = chosen.name[language];
  const pick = (v: { en: string; ar: string }) => (language === 'ar' ? v.ar : v.en);
  return (
    <details className="rounded-md border border-border bg-background text-xs" data-testid="about-mulhim" data-persona={chosen.code}
      onToggle={(e) => setOpen(e.currentTarget.open)}>
      <summary className="flex cursor-pointer items-center gap-1.5 px-3 py-2 font-semibold">
        <BookOpenText aria-hidden="true" className="size-3.5" />{t('assistant.about.open', { name })}
      </summary>
      {open ? (
        <div className="flex flex-col gap-2 border-t border-border px-3 py-2">
          {profile.isError ? <p role="alert" className="text-destructive">{t('assistant.about.unavailable')}</p> : null}
          {p && who ? (
            <>
              <p className="text-sm font-semibold"><bdi>{who.name.ar}</bdi> · <bdi>{who.name.en}</bdi></p>
              <p>{pick(who.introduction)}</p>
              <p><span className="font-semibold">{t('assistant.about.meaning')}: </span>{pick(who.meaning)}</p>
              {who.distinguished_from ? (
                <p><span className="font-semibold">{t('assistant.about.distinct')}: </span><bdi>{who.distinguished_from.ar}</bdi> ({who.distinguished_from.en})</p>
              ) : null}
              {who.linguistic_note ? (
                <div className="rounded border border-sand/50 bg-sand-subtle/50 p-2" data-testid="mulhim-interpretation">
                  <Badge variant="sand">{t('assistant.about.interpretation')}</Badge>
                  <p className="mt-1">{pick(who.linguistic_note)}</p>
                </div>
              ) : null}
              {who.distinguished_from ? (
                // The booklet's dictionary reference is about Al Mulhim's name.
                <p>
                  <span className="font-semibold">{t('assistant.about.reference')}: </span>
                  <a href={p.reference.url} target="_blank" rel="noreferrer noopener" className="inline-flex items-start gap-1 text-primary underline underline-offset-2">
                    <bdi>{p.reference.citation.split('. Retrieved')[0]}</bdi><ExternalLink aria-hidden="true" className="mt-0.5 size-3 shrink-0" />
                  </a>
                  <span className="block text-muted-foreground">{t('assistant.about.referenceNote')}</span>
                </p>
              ) : null}
              <p>{pick(who.self_description)}</p>
              <div>
                <p className="font-semibold">{t('assistant.about.canDo', { name })}</p>
                <ul className="list-disc ps-4">{p.capabilities.map((c) => <li key={c.code}>{pick(c)}</li>)}</ul>
              </div>
              <div>
                <p className="font-semibold">{t('assistant.about.limits')}</p>
                <ul className="list-disc ps-4">{p.limitations.map((c) => <li key={c.code}>{pick(c)}</li>)}</ul>
              </div>
              <p className="text-muted-foreground">{t('assistant.about.version', { version: p.version })}</p>
            </>
          ) : null}
        </div>
      ) : null}
    </details>
  );
}

/** Everything that is kept, by kind, with delete controls. No hidden model memory exists. */
export function MemoryPanel({ signedIn, guestExpires, guestConversationId, onGuestDeleted, onAllDeleted }: {
  signedIn: boolean;
  guestExpires: string | null;
  guestConversationId: string | null;
  onGuestDeleted: () => void;
  onAllDeleted: () => void;
}) {
  const { t } = useTranslation();
  const language = useAppLanguage();
  const to = usePreservedSearch();
  const [open, setOpen] = useState(false);
  const [confirm, setConfirm] = useState(false);
  const memory = useMemory(open && signedIn);
  const deleteAll = useDeleteAllConversations();
  const deleteGuest = useDeleteGuestConversation();
  const m = memory.data;
  return (
    <details className="rounded-md border border-border bg-background text-xs" data-testid="mulhim-memory"
      onToggle={(e) => setOpen(e.currentTarget.open)}>
      <summary className="flex cursor-pointer items-center gap-1.5 px-3 py-2 font-semibold">
        <Brain aria-hidden="true" className="size-3.5" />{t('assistant.memory.open')}
      </summary>
      <div className="flex flex-col gap-1.5 border-t border-border px-3 py-2">
        <p>{t('assistant.memory.intro')}</p>
        {signedIn && m ? (
          <ul className="list-disc ps-4" data-testid="memory-counts">
            {m.profile_version ? <li>{t('assistant.memory.identity', { version: m.profile_version })}</li> : null}
            <li>{t('assistant.memory.conversations', { count: m.conversations, messages: m.messages })}</li>
            <li>{t('assistant.memory.saved', { count: m.saved_research })}</li>
            <li>{t('assistant.memory.watchlist', { count: m.watchlist_items, rules: m.alert_rules })}</li>
            <li>{t('assistant.memory.thisDevice')}</li>
          </ul>
        ) : null}
        {!signedIn && guestExpires ? (
          <p>{t('assistant.memory.guest', { date: formatPeriod(guestExpires.slice(0, 10), guestExpires.slice(0, 10), language) })}</p>
        ) : null}
        <p className="text-muted-foreground">{t('assistant.memory.never')}</p>
        <p className="text-muted-foreground">{t('assistant.memory.retention')}</p>
        <div className="flex flex-wrap gap-2 pt-1">
          {signedIn ? (
            <>
              <Button size="sm" variant={confirm ? 'default' : 'outline'} disabled={deleteAll.isPending} data-testid="delete-all-conversations"
                onClick={() => {
                  if (!confirm) { setConfirm(true); return; }
                  deleteAll.mutate(undefined, { onSuccess: () => { setConfirm(false); onAllDeleted(); } });
                }}>
                <Trash2 aria-hidden="true" />{confirm ? t('assistant.memory.confirmDeleteAll') : t('assistant.memory.deleteAll')}
              </Button>
              <Link to={{ ...to('/library'), search: `${to('/library').search ? `${to('/library').search}&` : '?'}tab=saved` }}
                className="self-center text-primary underline underline-offset-2">{t('assistant.memory.openLibrary')}</Link>
            </>
          ) : guestConversationId ? (
            <Button size="sm" variant="outline" disabled={deleteGuest.isPending} data-testid="delete-guest-conversation"
              onClick={() => deleteGuest.mutate(guestConversationId, { onSuccess: onGuestDeleted })}>
              <Trash2 aria-hidden="true" />{t('assistant.memory.deleteGuest')}
            </Button>
          ) : null}
        </div>
        {deleteAll.isSuccess ? <p role="status">{t('assistant.memory.deleted', { count: deleteAll.data.deleted })}</p> : null}
      </div>
    </details>
  );
}
