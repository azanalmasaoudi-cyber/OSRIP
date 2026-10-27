import { MessageSquareText, RotateCcw, ShieldCheck, Smartphone } from 'lucide-react';
import { useEffect, useId, useMemo, useRef, useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';

import { usePhoneRequest, usePhoneVerify, useProviders, type PhoneChallenge, type PhoneOutcome } from '@/api/auth';
import { ApiRequestError } from '@/api/client';
import { Button } from '@/components/ui/button';
import { SelectField } from '@/components/ui/select';
import { useAppLanguage } from '@/lib/useAppLanguage';

/** Region for each offered country code, so names come from Intl in the page language. */
const REGION: Record<string, string> = {
  '+968': 'OM', '+971': 'AE', '+966': 'SA', '+974': 'QA', '+973': 'BH', '+965': 'KW',
  '+20': 'EG', '+44': 'GB', '+1': 'US', '+91': 'IN', '+92': 'PK', '+63': 'PH',
};

const ERROR_CODES = [
  'sms_unavailable', 'invalid_phone', 'invalid_country_code', 'sms_resend_cooldown', 'sms_number_limit', 'sms_client_limit',
  'sms_busy', 'sms_invalid_number', 'sms_undeliverable', 'sms_provider_unavailable', 'sms_code_incorrect', 'sms_code_expired',
  'sms_too_many_attempts', 'sms_challenge_invalid', 'invalid_code_format', 'phone_taken', 'phone_already_linked',
  'account_unavailable', 'too_many_requests', 'wrong_current_password', 'reauthentication_required',
] as const;
type ErrorCode = (typeof ERROR_CODES)[number];
/** After these, the only way forward is a new code or another method. */
const NEEDS_NEW_CODE = new Set<string>(['sms_code_expired', 'sms_too_many_attempts', 'sms_challenge_invalid']);
const OFFER_EMAIL = new Set<string>(['sms_unavailable', 'sms_undeliverable', 'sms_invalid_number', 'sms_provider_unavailable', 'sms_busy', 'sms_number_limit']);

function useCountdown(): [number, (seconds: number) => void] {
  const [until, setUntil] = useState(0);
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (until <= now) return;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [until, now]);
  return [Math.max(0, Math.ceil((until - now) / 1000)), (s: number) => { setNow(Date.now()); setUntil(Date.now() + s * 1000); }];
}

/**
 * Phone number → SMS code → verified. Used for registration and sign-in (purpose
 * "sign_in": an account is created only after the code is verified) and for adding a
 * number to the signed-in account (purpose "link"), including replacing a verified one
 * (`askPassword`: the current password is needed first). The code never passes through
 * anything but this form and the server.
 */
export function PhoneVerification({ purpose, askName = false, askPassword = false, onDone, onUseEmail }: {
  purpose: 'sign_in' | 'link';
  askName?: boolean;
  askPassword?: boolean;
  onDone: (status: PhoneOutcome) => void;
  onUseEmail?: () => void;
}) {
  const { t } = useTranslation();
  const language = useAppLanguage();
  const providers = useProviders();
  const request = usePhoneRequest();
  const verify = usePhoneVerify();
  const sms = providers.data?.sms;
  const [country, setCountry] = useState(sms?.default_country ?? '+968');
  const [number, setNumber] = useState('');
  const [name, setName] = useState('');
  const [password, setPassword] = useState('');
  const [code, setCode] = useState('');
  const [challenge, setChallenge] = useState<PhoneChallenge | null>(null);
  const [remaining, startCountdown] = useCountdown();
  const codeRef = useRef<HTMLInputElement>(null);
  const ids = { number: useId(), code: useId(), name: useId(), hint: useId(), codeHint: useId(), password: useId() };

  const regions = useMemo(() => {
    let names: Intl.DisplayNames | null = null;
    try { names = new Intl.DisplayNames([language], { type: 'region' }); } catch { names = null; }
    return (providers.data?.country_codes ?? Object.keys(REGION)).map((c) => ({
      value: c, label: `${(REGION[c] && names?.of(REGION[c])) || c} (${c})`,
    }));
  }, [providers.data?.country_codes, language]);

  useEffect(() => { if (challenge) codeRef.current?.focus(); }, [challenge]);

  if (providers.isPending) return null;
  if (!sms?.available) {
    return (
      <div className="flex flex-col gap-3 rounded-lg border border-dashed border-border-strong/60 bg-card p-5" data-testid="phone-unavailable">
        <p className="flex items-start gap-2 text-sm font-semibold"><Smartphone aria-hidden="true" className="mt-0.5 size-4 shrink-0 text-muted-foreground" />{t('phone.unavailableTitle')}</p>
        <p className="text-sm text-muted-foreground">{t('phone.unavailable')}</p>
        {onUseEmail ? <Button type="button" variant="outline" className="w-fit" onClick={onUseEmail}>{t('phone.useEmail')}</Button> : null}
      </div>
    );
  }

  const error = (verify.error ?? request.error) as unknown;
  const apiError = error instanceof ApiRequestError ? error : null;
  const errorCode: ErrorCode | 'other' | null = apiError ? (ERROR_CODES.find((c) => c === apiError.code) ?? 'other') : error ? 'other' : null;
  const details = (apiError?.details ?? {}) as { attempts_left?: number; retry_after?: number; minutes?: number };

  const send = (event?: FormEvent) => {
    event?.preventDefault();
    verify.reset();
    request.mutate({ country_code: country, number, purpose, password: askPassword ? password : undefined }, {
      onSuccess: (c) => { setChallenge(c); setCode(''); startCountdown(c.resend_after); },
      onError: (e) => {
        if (e instanceof ApiRequestError && e.code === 'sms_resend_cooldown') {
          startCountdown(Number((e.details as { retry_after?: number } | undefined)?.retry_after ?? 60));
        }
      },
    });
  };
  const check = (event: FormEvent) => {
    event.preventDefault();
    if (!challenge) return;
    verify.mutate({ challenge_id: challenge.challenge_id, code, display_name: askName ? name : undefined }, {
      onSuccess: (r) => onDone(r.status),
    });
  };
  const changeNumber = () => { setChallenge(null); setCode(''); request.reset(); verify.reset(); };

  const message = errorCode === null ? null
    : errorCode === 'other' ? (error instanceof Error ? error.message : t('phone.error.other'))
    : t(`phone.error.${errorCode}`, { n: details.attempts_left ?? details.retry_after ?? details.minutes ?? 0 });

  return (
    <div className="flex flex-col gap-4" data-testid="phone-verification" data-step={challenge ? 'code' : 'number'}>
      {sms.status === 'test' ? (
        <p className="rounded-md border border-dashed border-synthetic-border bg-synthetic px-3 py-2 text-xs text-synthetic-foreground" data-testid="sms-test-mode">
          {t('phone.testMode')}
        </p>
      ) : null}
      {!challenge ? (
        <form onSubmit={send} className="flex flex-col gap-4" noValidate data-testid="phone-number-form">
          {askName ? (
            <div className="flex flex-col gap-1.5">
              <label htmlFor={ids.name} className="text-sm font-medium">{t('account.name')}</label>
              <input id={ids.name} autoComplete="name" value={name} onChange={(e) => setName(e.target.value)} maxLength={120}
                className="h-10 rounded-md border border-border-strong bg-card px-3 text-sm" />
            </div>
          ) : null}
          <div className="grid gap-3 sm:grid-cols-[minmax(0,11rem)_minmax(0,1fr)]">
            <SelectField label={t('phone.country')} value={country} onValueChange={setCountry} options={regions} data-testid="phone-country" labelClassName="text-sm font-medium text-foreground" />
            <div className="flex min-w-0 flex-col gap-1.5">
              <label htmlFor={ids.number} className="text-sm font-medium">{t('phone.number')}</label>
              <input id={ids.number} type="tel" inputMode="tel" autoComplete="tel-national" dir="ltr" value={number}
                onChange={(e) => setNumber(e.target.value)} placeholder={country === '+968' ? '9123 4567' : ''}
                aria-describedby={ids.hint} data-testid="phone-number"
                className="h-10 rounded-md border border-border-strong bg-card px-3 text-start text-sm tabular-nums" />
            </div>
          </div>
          <p id={ids.hint} className="text-xs text-muted-foreground">{country === '+968' ? t('phone.omanHint') : t('phone.hint')}</p>
          {askPassword ? (
            <div className="flex flex-col gap-1.5">
              <label htmlFor={ids.password} className="text-sm font-medium">{t('account.currentPassword')}</label>
              <input id={ids.password} type="password" autoComplete="current-password" dir="ltr" value={password}
                onChange={(e) => setPassword(e.target.value)} data-testid="phone-password"
                className="h-10 rounded-md border border-border-strong bg-card px-3 text-sm" />
            </div>
          ) : null}
          {message ? <p role="alert" className="text-sm text-destructive" data-testid="phone-error" data-code={errorCode}>{message}</p> : null}
          {errorCode && OFFER_EMAIL.has(errorCode) && onUseEmail ? (
            <Button type="button" variant="outline" size="sm" className="w-fit" onClick={onUseEmail}>{t('phone.useEmail')}</Button>
          ) : null}
          {purpose === 'sign_in' ? <p className="text-xs text-muted-foreground">{t('phone.ordinaryAccess')}</p> : null}
          <Button type="submit" disabled={request.isPending || number.replace(/\D/g, '').length < 4 || remaining > 0 || (askPassword && !password)} data-testid="phone-send">
            <MessageSquareText aria-hidden="true" />
            {remaining > 0 ? t('phone.resendIn', { n: remaining }) : request.isPending ? t('phone.sending') : t('phone.sendCode')}
          </Button>
        </form>
      ) : (
        <form onSubmit={check} className="flex flex-col gap-4" noValidate data-testid="phone-code-form">
          <p role="status" className="text-sm" data-testid="phone-sent">
            {t('phone.sentTo', { phone: challenge.phone_masked, minutes: Math.round(challenge.expires_in / 60) })}
          </p>
          <div className="flex flex-col gap-1.5">
            <label htmlFor={ids.code} className="text-sm font-medium">{t('phone.code')}</label>
            <input id={ids.code} ref={codeRef} inputMode="numeric" autoComplete="one-time-code" pattern="[0-9]*" dir="ltr"
              maxLength={10} value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, ''))} aria-describedby={ids.codeHint}
              data-testid="phone-code"
              className="h-12 w-full max-w-[12rem] rounded-md border border-border-strong bg-card px-3 text-center font-mono text-xl tracking-[0.35em] tabular-nums" />
            <p id={ids.codeHint} className="text-xs text-muted-foreground">{t('phone.codeHint', { n: challenge.max_attempts })}</p>
          </div>
          {message ? <p role="alert" className="text-sm text-destructive" data-testid="phone-error" data-code={errorCode}>{message}</p> : null}
          {errorCode && OFFER_EMAIL.has(errorCode) && onUseEmail ? (
            <Button type="button" variant="outline" size="sm" className="w-fit" onClick={onUseEmail}>{t('phone.useEmail')}</Button>
          ) : null}
          <Button type="submit" disabled={verify.isPending || code.length < 4 || (errorCode !== null && NEEDS_NEW_CODE.has(errorCode))} data-testid="phone-verify">
            <ShieldCheck aria-hidden="true" />{verify.isPending ? t('phone.verifying') : t('phone.verify')}
          </Button>
          <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-sm">
            <Button type="button" variant="ghost" size="sm" onClick={() => send()} disabled={remaining > 0 || request.isPending} data-testid="phone-resend">
              <RotateCcw aria-hidden="true" />
              {remaining > 0 ? t('phone.resendIn', { n: remaining }) : t('phone.resend')}
            </Button>
            <button type="button" onClick={changeNumber} className="text-primary underline underline-offset-2" data-testid="phone-change">{t('phone.changeNumber')}</button>
          </div>
        </form>
      )}
    </div>
  );
}
