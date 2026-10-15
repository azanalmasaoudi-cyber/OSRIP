import { CheckCircle2, KeyRound, LogIn, Mail, ShieldCheck, Trash2, UserPlus } from 'lucide-react';
import { useEffect, useId, useRef, useState, type FormEvent, type InputHTMLAttributes, type ReactNode } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router';
import { useTranslation } from 'react-i18next';

import {
  hasPermission,
  OIDC_PROVIDERS,
  oidcStartUrl,
  ROLES,
  useAdminUsers,
  useChangePassword,
  useConsumeMagicLink,
  useDevOutbox,
  useEmailRequest,
  useConfirmEmailLink,
  useDevSmsOutbox,
  useIdentities,
  useLinkEmail,
  useLogin,
  useMe,
  useProviders,
  useRegister,
  useResetPassword,
  useSetRole,
  useUnlinkIdentity,
  useVerifyEmail,
  type OidcProvider,
} from '@/api/auth';
import { ApiRequestError } from '@/api/client';
import { adapterKind } from '@/api/config';
import { PhoneVerification } from '@/components/auth/PhoneVerification';
import { PageHeader } from '@/components/common/PageHeader';
import { SettingsSection } from '@/components/settings/SettingsSection';
import { StatePanel } from '@/components/common/StatePanel';
import { Badge } from '@/components/ui/badge';
import { Button, buttonVariants } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Segmented } from '@/components/ui/segmented';
import { cn } from '@/lib/utils';
import { usePreservedSearch } from '@/state/usePreservedSearch';

// ------------------------------------------------------------------ shared pieces

function Field({ label, hint, ...props }: { label: string; hint?: string } & InputHTMLAttributes<HTMLInputElement>) {
  const id = useId();
  const hintId = useId();
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={id} className="text-sm font-medium">{label}</label>
      <input id={id} aria-describedby={hint ? hintId : undefined}
        className="h-10 rounded-md border border-border-strong bg-card px-3 text-sm" {...props} />
      {hint ? <p id={hintId} className="text-xs text-muted-foreground">{hint}</p> : null}
    </div>
  );
}

function ErrorText({ error }: { error: unknown }) {
  if (!error) return null;
  const message = error instanceof Error ? error.message : 'Request failed.';
  return <p role="alert" className="text-sm text-destructive">{message}</p>;
}

function Notice({ tone = 'info', children }: { tone?: 'info' | 'success'; children: ReactNode }) {
  return (
    <p role="status" className={cn('rounded-md border px-3 py-2 text-sm',
      tone === 'success' ? 'border-verified-border bg-verified text-verified-foreground' : 'border-sand/50 bg-sand-subtle text-sand-foreground')}>
      {children}
    </p>
  );
}

function RequiresApi({ title }: { title: string }) {
  const { t } = useTranslation();
  return (
    <>
      <PageHeader title={title} />
      <StatePanel kind="not_implemented"><p className="text-sm text-muted-foreground">{t('auth.requiresApi')}</p></StatePanel>
    </>
  );
}

const PROVIDER_LABEL: Record<OidcProvider, string> = { google: 'Google', microsoft: 'Microsoft' };

const OIDC_ERRORS = [
  'sign_in_failed', 'provider_declined', 'invalid_state', 'browser_mismatch', 'token_exchange_failed',
  'invalid_id_token', 'email_not_verified_by_provider', 'identity_in_use', 'account_unavailable', 'provider_unavailable',
] as const;
function oidcErrorKey(code: string): (typeof OIDC_ERRORS)[number] {
  return OIDC_ERRORS.find((e) => e === code) ?? 'sign_in_failed';
}

function ProviderButtons({ intent }: { intent: 'sign_in' | 'link' }) {
  const { t } = useTranslation();
  const providers = useProviders();
  if (!providers.data) return null;
  return (
    <ul className="flex flex-col gap-2" data-testid="oidc-providers">
      {OIDC_PROVIDERS.map((p) => (
        <li key={p}>
          {providers.data.oidc[p] ? (
            <a href={oidcStartUrl(p, intent)} className={cn(buttonVariants({ variant: 'outline' }), 'w-full')} data-testid={`oidc-${p}`}>
              <ShieldCheck aria-hidden="true" />
              {intent === 'link' ? t('account.linkWith', { provider: PROVIDER_LABEL[p] }) : t('account.continueWith', { provider: PROVIDER_LABEL[p] })}
            </a>
          ) : (
            // Not a button: an unconfigured provider is reported, never faked.
            <p className="rounded-md border border-dashed border-border-strong/50 px-3 py-2 text-sm text-muted-foreground" data-testid={`oidc-${p}-unconfigured`}>
              {t('account.notConfigured', { provider: PROVIDER_LABEL[p] })}
            </p>
          )}
        </li>
      ))}
    </ul>
  );
}

/** The chosen sign-in or registration method lives in ?method= (replaced, not pushed). */
function useMethodParam<T extends string>(values: readonly T[], fallback: T): [T, (value: T) => void] {
  const [params, setParams] = useSearchParams();
  const raw = params.get('method');
  const value = values.find((v) => v === raw) ?? fallback;
  const set = (next: T) => setParams((prev) => {
    const updated = new URLSearchParams(prev);
    if (next === fallback) updated.delete('method'); else updated.set('method', next);
    return updated;
  }, { replace: true });
  return [value, set];
}

function useTokenFromUrl(): string | null {
  const [params] = useSearchParams();
  const [token] = useState<string | null>(() => params.get('token'));
  useEffect(() => {
    // Remove the token from the address bar and history once read.
    if (params.has('token')) window.history.replaceState(null, '', window.location.pathname);
  }, [params]);
  return token;
}

// ------------------------------------------------------------------ sign in

export function SignInPage() {
  const { t } = useTranslation();
  const login = useLogin();
  const navigate = useNavigate();
  const to = usePreservedSearch();
  const [params] = useSearchParams();
  const providers = useProviders();
  const magic = useEmailRequest('/auth/magic-link');
  const resend = useEmailRequest('/auth/verify-email/resend');
  const [method, setMethod] = useMethodParam(['password', 'magic', 'phone'] as const, 'password');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');

  if (adapterKind !== 'http') return <RequiresApi title={t('auth.title')} />;

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (method === 'password') {
      login.mutate({ email, password }, { onSuccess: () => void navigate(to('/account')) });
    } else {
      magic.mutate(email);
    }
  };
  const unverified = login.error instanceof ApiRequestError && login.error.code === 'email_not_verified';
  const notice = params.get('notice');
  const error = params.get('error');

  return (
    <>
      <PageHeader title={t('auth.title')} intro={t('auth.intro')} />
      <div className="grid max-w-3xl gap-6 md:grid-cols-[minmax(0,1fr)_minmax(0,18rem)]">
        <div className="surface-card flex flex-col gap-4 p-6">
          {notice === 'link_required' ? (
            <Notice>{t('account.linkRequired', { provider: PROVIDER_LABEL[(params.get('provider') as OidcProvider) ?? 'google'] ?? '' })}</Notice>
          ) : null}
          {error ? <p role="alert" className="text-sm text-destructive" data-testid="oidc-error">{t(`account.oidcError.${oidcErrorKey(error)}`)}</p> : null}
          <Segmented label={t('account.method')} value={method} onChange={setMethod} testId="sign-in-method" options={[
            { value: 'password', label: t('account.methodPassword') },
            { value: 'magic', label: t('account.methodMagic'), note: providers.data?.magic_link === false ? t('phone.unavailableShort') : undefined },
            { value: 'phone', label: t('phone.methodPhone'), note: providers.data?.sms.available === false ? t('phone.unavailableShort') : undefined },
          ]} />
          {method === 'phone' ? (
            <PhoneVerification purpose="sign_in" onDone={() => void navigate(to('/account'))} onUseEmail={() => setMethod('password')} />
          ) : (
        <form onSubmit={submit} className="flex flex-col gap-4" noValidate data-testid="sign-in-form">
          {/* Password sign-in accepts a username or an e-mail address; links need an address. */}
          <Field label={method === 'password' ? t('auth.identifier') : t('auth.email')} type={method === 'password' ? 'text' : 'email'}
            autoComplete="username" autoCapitalize="none" spellCheck={false} required value={email}
            onChange={(e) => setEmail(e.target.value)} dir="ltr" data-testid="sign-in-identifier" />
          {method === 'password' ? (
            <Field label={t('auth.password')} type="password" autoComplete="current-password" required value={password}
              onChange={(e) => setPassword(e.target.value)} dir="ltr" />
          ) : (
            <p className="text-xs text-muted-foreground">{t('account.magicHint')}</p>
          )}
          {method === 'password' ? <ErrorText error={login.error} /> : <ErrorText error={magic.error} />}
          {unverified ? (
            <Button type="button" variant="outline" size="sm" className="w-fit" onClick={() => resend.mutate(email)} disabled={resend.isPending}>
              <Mail aria-hidden="true" />{t('account.resend')}
            </Button>
          ) : null}
          {resend.isSuccess ? <Notice>{t('account.checkInbox')}</Notice> : null}
          {magic.isSuccess && method === 'magic' ? <Notice>{t('account.checkInbox')}</Notice> : null}
          <Button type="submit" disabled={login.isPending || magic.isPending || !email || (method === 'password' && !password)}>
            {method === 'password' ? <LogIn aria-hidden="true" /> : <Mail aria-hidden="true" />}
            {method === 'password'
              ? (login.isPending ? t('auth.submitting') : t('auth.submit'))
              : t('account.sendLink')}
          </Button>
        </form>
          )}
          <div className="flex flex-wrap justify-between gap-2 text-sm">
            <Link to={to('/forgot-password')} className="text-primary underline underline-offset-2">{t('account.forgot')}</Link>
            <Link to={to('/register')} className="text-primary underline underline-offset-2">{t('account.createAccount')}</Link>
          </div>
        </div>
        <section aria-labelledby="providers-heading" className="flex flex-col gap-3">
          <h2 id="providers-heading" className="text-sm font-semibold">{t('account.otherMethods')}</h2>
          <ProviderButtons intent="sign_in" />
          {providers.data?.email_delivery === 'outbox' ? <DevMailHint /> : null}
          {providers.data?.email_delivery === 'disabled' ? <Notice>{t('account.emailDisabled')}</Notice> : null}
        </section>
      </div>
    </>
  );
}

function DevMailHint() {
  const { t } = useTranslation();
  const to = usePreservedSearch();
  return (
    <p className="rounded-md border border-dashed border-synthetic-border bg-synthetic px-3 py-2 text-xs text-synthetic-foreground">
      {t('account.devMailHint')} <Link to={to('/dev/mail')} className="underline">{t('account.devMailLink')}</Link>
    </p>
  );
}

// ------------------------------------------------------------------ register

export function RegisterPage() {
  const { t } = useTranslation();
  const register = useRegister();
  const providers = useProviders();
  const to = usePreservedSearch();
  const navigate = useNavigate();
  const [method, setMethod] = useMethodParam(['email', 'phone'] as const, 'email');
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');

  if (adapterKind !== 'http') return <RequiresApi title={t('account.registerTitle')} />;
  const submit = (event: FormEvent) => {
    event.preventDefault();
    register.mutate({ email, display_name: name, password });
  };

  return (
    <>
      <PageHeader title={t('account.registerTitle')} intro={t('account.registerIntro')} />
      <div className="surface-card flex max-w-md flex-col gap-5 p-6" data-testid="register-card">
      <Segmented label={t('account.registerMethod')} value={method} onChange={setMethod} testId="register-method" options={[
        { value: 'email', label: t('account.methodEmail'), note: providers.data?.registration === false ? t('phone.unavailableShort') : undefined },
        { value: 'phone', label: t('phone.methodPhone'), note: providers.data?.sms.available === false ? t('phone.unavailableShort') : undefined },
      ]} />
      {method === 'phone' ? (
        <PhoneVerification purpose="sign_in" askName onDone={() => void navigate(to('/account'))} onUseEmail={() => setMethod('email')} />
      ) : providers.data?.registration === false ? <Notice>{t('account.emailDisabled')}</Notice> : register.isSuccess ? (
        <div className="flex max-w-lg flex-col gap-3" data-testid="register-done">
          <Notice tone="success">{t('account.checkInbox')}</Notice>
          {providers.data?.email_delivery === 'outbox' ? <DevMailHint /> : null}
        </div>
      ) : (
        <form onSubmit={submit} className="flex flex-col gap-4" noValidate data-testid="register-form">
          <Field label={t('account.name')} autoComplete="name" required value={name} onChange={(e) => setName(e.target.value)} />
          <Field label={t('auth.email')} type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} dir="ltr" />
          <Field label={t('auth.password')} type="password" autoComplete="new-password" required minLength={12} value={password}
            onChange={(e) => setPassword(e.target.value)} dir="ltr" hint={t('account.passwordHint')} />
          <ErrorText error={register.error} />
          <p className="text-xs text-muted-foreground">{t('account.ordinaryAccess')}</p>
          <Button type="submit" disabled={register.isPending || !name || !email || password.length < 12}>
            <UserPlus aria-hidden="true" />{t('account.createAccount')}
          </Button>
        </form>
      )}
      <Link to={to('/sign-in')} className="text-sm text-primary underline underline-offset-2">{t('account.haveAccount')}</Link>
      </div>
    </>
  );
}

// ------------------------------------------------------------------ links from e-mail

export function VerifyEmailPage() {
  const { t } = useTranslation();
  const token = useTokenFromUrl();
  const verify = useVerifyEmail();
  const to = usePreservedSearch();
  const started = useRef(false);
  useEffect(() => {
    if (token && !started.current) {
      started.current = true;
      verify.mutate(token);
    }
  }, [token, verify]);
  return (
    <>
      <PageHeader title={t('account.verifyTitle')} />
      <div className="flex max-w-lg flex-col gap-3" data-testid="verify-result">
        {!token ? <Notice>{t('account.missingToken')}</Notice> : null}
        {verify.isPending ? <StatePanel kind="loading" skeleton="lines" /> : null}
        {verify.isSuccess ? <Notice tone="success"><CheckCircle2 aria-hidden="true" className="me-1 inline size-4" />{t('account.verified')}</Notice> : null}
        <ErrorText error={verify.error} />
        <Link to={to('/sign-in')} className={cn(buttonVariants({ variant: 'outline' }), 'w-fit')}>{t('auth.signIn')}</Link>
      </div>
    </>
  );
}

export function ForgotPasswordPage() {
  const { t } = useTranslation();
  const forgot = useEmailRequest('/auth/password/forgot');
  const [email, setEmail] = useState('');
  return (
    <>
      <PageHeader title={t('account.forgotTitle')} intro={t('account.forgotIntro')} />
      <form onSubmit={(e) => { e.preventDefault(); forgot.mutate(email); }} noValidate
        className="flex max-w-md flex-col gap-4 rounded-lg border border-border bg-card p-6" data-testid="forgot-form">
        <Field label={t('auth.email')} type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} dir="ltr" />
        <ErrorText error={forgot.error} />
        {forgot.isSuccess ? <Notice tone="success">{t('account.checkInbox')}</Notice> : null}
        <Button type="submit" disabled={forgot.isPending || !email}><KeyRound aria-hidden="true" />{t('account.sendResetLink')}</Button>
      </form>
    </>
  );
}

export function ResetPasswordPage() {
  const { t } = useTranslation();
  const token = useTokenFromUrl();
  const reset = useResetPassword();
  const to = usePreservedSearch();
  const [password, setPassword] = useState('');
  return (
    <>
      <PageHeader title={t('account.resetTitle')} intro={t('account.resetIntro')} />
      {!token ? <Notice>{t('account.missingToken')}</Notice> : reset.isSuccess ? (
        <div className="flex max-w-lg flex-col gap-3" data-testid="reset-done">
          <Notice tone="success">{t('account.resetDone')}</Notice>
          <Link to={to('/sign-in')} className={cn(buttonVariants({ variant: 'outline' }), 'w-fit')}>{t('auth.signIn')}</Link>
        </div>
      ) : (
        <form onSubmit={(e) => { e.preventDefault(); reset.mutate({ token, password }); }} noValidate
          className="flex max-w-md flex-col gap-4 rounded-lg border border-border bg-card p-6" data-testid="reset-form">
          <Field label={t('account.newPassword')} type="password" autoComplete="new-password" required minLength={12}
            value={password} onChange={(e) => setPassword(e.target.value)} dir="ltr" hint={t('account.passwordHint')} />
          <ErrorText error={reset.error} />
          <Button type="submit" disabled={reset.isPending || password.length < 12}><KeyRound aria-hidden="true" />{t('account.setPassword')}</Button>
        </form>
      )}
    </>
  );
}

export function MagicLinkPage() {
  const { t } = useTranslation();
  const token = useTokenFromUrl();
  const consume = useConsumeMagicLink();
  const navigate = useNavigate();
  const to = usePreservedSearch();
  // A button, not an automatic request: mail scanners that open links must not spend the token.
  return (
    <>
      <PageHeader title={t('account.magicTitle')} intro={t('account.magicIntro')} />
      {!token ? <Notice>{t('account.missingToken')}</Notice> : (
        <div className="flex max-w-md flex-col gap-3">
          <Button onClick={() => consume.mutate(token, { onSuccess: () => void navigate(to('/account')) })}
            disabled={consume.isPending || consume.isSuccess} className="w-fit" data-testid="magic-sign-in">
            <LogIn aria-hidden="true" />{t('auth.signIn')}
          </Button>
          <ErrorText error={consume.error} />
        </div>
      )}
    </>
  );
}

// ------------------------------------------------------------------ account

export function AccountPage() {
  const { t } = useTranslation();
  const me = useMe();
  const [params] = useSearchParams();
  const identities = useIdentities(Boolean(me.data?.authenticated));
  const unlink = useUnlinkIdentity();
  const to = usePreservedSearch();
  const [phoneLinkedNow, setPhoneLinkedNow] = useState(false);

  // Settings stored in this browser are available signed in or not, and without the API.
  if (adapterKind !== 'http') return <><RequiresApi title={t('account.title')} /><div className="mt-6 max-w-3xl"><SettingsSection /></div></>;
  if (me.isPending) return <StatePanel kind="loading" skeleton="lines" />;
  if (!me.data?.authenticated) {
    return (
      <>
        <PageHeader title={t('account.title')} />
        <StatePanel kind="restricted">
          <Link to={to('/sign-in')} className="text-sm text-primary underline">{t('auth.signIn')}</Link>
        </StatePanel>
        <div className="mt-6 max-w-3xl"><SettingsSection /></div>
      </>
    );
  }
  const signedIn = params.get('signed_in');
  const linked = params.get('linked');

  if (me.data.password_change_required) {
    // A temporary password: nothing else on the account works until it is replaced.
    return (
      <>
        <PageHeader title={t('account.changeRequiredTitle')} intro={t('account.changeRequired')} />
        <div className="max-w-md"><ChangePassword required /></div>
      </>
    );
  }

  return (
    <>
      <PageHeader title={t('account.title')} intro={t('account.intro')} />
      <div className="flex max-w-3xl flex-col gap-6" data-testid="account-page">
        {signedIn ? <Notice tone="success">{t('account.signedInWith', { provider: PROVIDER_LABEL[signedIn as OidcProvider] ?? signedIn })}</Notice> : null}
        {linked ? <Notice tone="success">{t('account.linkedNotice', { provider: PROVIDER_LABEL[linked as OidcProvider] ?? linked })}</Notice> : null}
        <Card className="p-5">
          <dl className="grid gap-x-4 gap-y-2 text-sm sm:grid-cols-[auto_1fr]">
            <dt className="text-muted-foreground">{t('account.name')}</dt><dd>{me.data.display_name}</dd>
            {me.data.username ? (
              <><dt className="text-muted-foreground">{t('account.username')}</dt><dd dir="ltr" data-testid="account-username">{me.data.username}</dd></>
            ) : null}
            <dt className="text-muted-foreground">{t('auth.email')}</dt>
            <dd data-testid="account-email">
              {me.data.email ? (
                <span dir="ltr">{me.data.email}{' '}
                  <Badge variant={me.data.email_verified ? 'verified' : 'sand'}>{me.data.email_verified ? t('account.emailVerified') : t('account.emailUnverified')}</Badge>
                </span>
              ) : <span className="text-muted-foreground">{t('account.noEmail')}</span>}
            </dd>
            <dt className="text-muted-foreground">{t('phone.number')}</dt>
            <dd data-testid="account-phone">
              {me.data.phone ? (
                <span><span dir="ltr" className="tabular-nums">{me.data.phone}</span>{' '}<Badge variant="verified">{t('phone.verified')}</Badge></span>
              ) : <span className="text-muted-foreground">{t('phone.none')}</span>}
            </dd>
            <dt className="text-muted-foreground">{t('account.roles')}</dt>
            <dd data-testid="account-roles">{me.data.roles.map((r) => t(`account.role.${r as 'viewer'}`)).join(document.documentElement.lang === 'ar' ? '، ' : ', ') || '—'}</dd>
          </dl>
          <p className="mt-3 text-xs text-muted-foreground">{t('account.rolesNote')}</p>
        </Card>
        {/* Stays mounted just after linking so its confirmation is shown. */}
        {!me.data.phone || phoneLinkedNow ? <AddPhone onLinked={() => setPhoneLinkedNow(true)} /> : null}
        {!me.data.email || !me.data.email_verified ? <AddEmail /> : null}
        {me.data.has_password ? <ChangePassword /> : null}
        <section aria-labelledby="linked-heading" className="flex flex-col gap-3">
          <h2 id="linked-heading" className="text-lg font-semibold">{t('account.linkedHeading')}</h2>
          <p className="text-sm text-muted-foreground">{t('account.linkedIntro')}</p>
          {identities.data && identities.data.length > 0 ? (
            <ul className="flex flex-col gap-2" data-testid="identities">
              {identities.data.map((i) => (
                <li key={i.id} className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-border bg-card px-3 py-2 text-sm">
                  <span>{PROVIDER_LABEL[i.provider]} <span className="text-muted-foreground" dir="ltr">{i.email}</span></span>
                  <Button variant="ghost" size="sm" onClick={() => unlink.mutate(i.id)} disabled={unlink.isPending}>
                    <Trash2 aria-hidden="true" />{t('account.unlink')}
                  </Button>
                </li>
              ))}
            </ul>
          ) : <p className="text-sm text-muted-foreground">{t('account.noLinked')}</p>}
          <ErrorText error={unlink.error} />
          <ProviderButtons intent="link" />
        </section>
        <SettingsSection />
      </div>
    </>
  );
}

function ChangePassword({ required = false }: { required?: boolean }) {
  const { t } = useTranslation();
  const change = useChangePassword();
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  return (
    <section aria-labelledby="change-password-heading" className="surface-card flex flex-col gap-3 p-5" data-testid="change-password">
      <h2 id="change-password-heading" className="text-lg font-semibold">{t('account.changePasswordTitle')}</h2>
      <p className="text-sm text-muted-foreground">{t('account.changePasswordIntro')}</p>
      {change.isSuccess && !required ? <Notice tone="success">{t('account.passwordChanged')}</Notice> : null}
      <form
        className="flex flex-col gap-3"
        onSubmit={(e) => {
          e.preventDefault();
          change.mutate({ current_password: current, new_password: next }, { onSuccess: () => { setCurrent(''); setNext(''); } });
        }}
      >
        <Field label={t('account.currentPassword')} type="password" autoComplete="current-password" required value={current}
          onChange={(e) => setCurrent(e.target.value)} dir="ltr" />
        <Field label={t('account.newPassword')} type="password" autoComplete="new-password" required minLength={12} value={next}
          hint={t('account.passwordHint')} onChange={(e) => setNext(e.target.value)} dir="ltr" />
        <ErrorText error={change.error} />
        <Button type="submit" className="w-fit" disabled={change.isPending || !current || next.length < 12} data-testid="change-password-submit">
          <KeyRound aria-hidden="true" />{t('account.changePassword')}
        </Button>
      </form>
    </section>
  );
}

function AddPhone({ onLinked }: { onLinked: () => void }) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const [done, setDone] = useState(false);
  return (
    <section aria-labelledby="add-phone-heading" className="surface-card flex flex-col gap-3 p-5" data-testid="add-phone">
      <h2 id="add-phone-heading" className="text-lg font-semibold">{t('phone.addTitle')}</h2>
      <p className="text-sm text-muted-foreground">{t('phone.addIntro')}</p>
      {done ? <Notice tone="success">{t('phone.linked')}</Notice> : open ? (
        <PhoneVerification purpose="link" onDone={() => { setDone(true); onLinked(); }} />
      ) : (
        <Button variant="outline" className="w-fit" onClick={() => setOpen(true)} data-testid="add-phone-open">{t('phone.addButton')}</Button>
      )}
    </section>
  );
}

function AddEmail() {
  const { t } = useTranslation();
  const link = useLinkEmail();
  const providers = useProviders();
  const [email, setEmail] = useState('');
  return (
    <section aria-labelledby="add-email-heading" className="surface-card flex flex-col gap-3 p-5" data-testid="add-email">
      <h2 id="add-email-heading" className="text-lg font-semibold">{t('account.addEmailTitle')}</h2>
      <p className="text-sm text-muted-foreground">{t('account.addEmailIntro')}</p>
      {providers.data?.email_delivery === 'disabled' ? <Notice>{t('account.emailDisabled')}</Notice> : link.isSuccess ? (
        <Notice tone="success">{t('account.checkInbox')}</Notice>
      ) : (
        <form onSubmit={(e) => { e.preventDefault(); link.mutate(email); }} noValidate className="flex flex-col gap-3">
          <Field label={t('auth.email')} type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} dir="ltr" />
          <ErrorText error={link.error} />
          <Button type="submit" variant="outline" className="w-fit" disabled={link.isPending || !email}><Mail aria-hidden="true" />{t('account.sendConfirmLink')}</Button>
        </form>
      )}
    </section>
  );
}

export function LinkEmailPage() {
  const { t } = useTranslation();
  const token = useTokenFromUrl();
  const confirm = useConfirmEmailLink();
  const to = usePreservedSearch();
  // A button, not an automatic request: mail scanners that open links must not spend the token.
  return (
    <>
      <PageHeader title={t('account.linkEmailTitle')} intro={t('account.linkEmailIntro')} />
      {!token ? <Notice>{t('account.missingToken')}</Notice> : (
        <div className="flex max-w-md flex-col gap-3" data-testid="link-email">
          {confirm.isSuccess ? <Notice tone="success">{t('account.emailLinked')}</Notice> : (
            <Button onClick={() => confirm.mutate(token)} disabled={confirm.isPending} className="w-fit" data-testid="link-email-confirm">
              <CheckCircle2 aria-hidden="true" />{t('account.confirmEmail')}
            </Button>
          )}
          <ErrorText error={confirm.error} />
          <Link to={to('/account')} className={cn(buttonVariants({ variant: 'outline' }), 'w-fit')}>{t('account.title')}</Link>
        </div>
      )}
    </>
  );
}

// ------------------------------------------------------------------ administration

export function AdminUsersPage() {
  const { t } = useTranslation();
  const me = useMe();
  const allowed = hasPermission(me.data, 'user.manage');
  const users = useAdminUsers(adapterKind === 'http' && allowed);
  const setRole = useSetRole();
  // Optimistic state per checkbox until the server answers; the list is refetched afterwards.
  const [pending, setPending] = useState<Record<string, boolean>>({});

  if (adapterKind !== 'http') return <RequiresApi title={t('account.adminTitle')} />;
  return (
    <>
      <PageHeader title={t('account.adminTitle')} intro={t('account.adminIntro')} />
      {!allowed ? <StatePanel kind="restricted" /> : users.isPending ? <StatePanel kind="loading" skeleton="lines" /> : users.isError ? (
        <StatePanel kind="error" detail={users.error.message} onRetry={() => void users.refetch()} />
      ) : (
        <div className="relative overflow-x-auto rounded-lg border border-border bg-card">
          <table className="w-full min-w-[44rem] text-sm" data-testid="admin-users">
            <caption className="px-4 pt-3 text-start text-xs text-muted-foreground">{t('account.adminCaption')}</caption>
            <thead>
              <tr className="border-b border-border-strong/40 text-xs text-muted-foreground">
                <th scope="col" className="px-4 py-2 text-start font-medium">{t('account.name')}</th>
                <th scope="col" className="px-2 py-2 text-start font-medium">{t('auth.email')}</th>
                <th scope="col" className="px-2 py-2 text-start font-medium">{t('account.createdVia')}</th>
                {ROLES.map((r) => <th key={r} scope="col" className="px-2 py-2 text-center font-medium">{t(`account.role.${r}`)}</th>)}
              </tr>
            </thead>
            <tbody>
              {users.data.map((u) => (
                <tr key={u.id} className="border-b border-border last:border-0" data-email={u.email ?? undefined}>
                  <th scope="row" className="px-4 py-2 text-start font-medium">{u.display_name}</th>
                  <td className="px-2 py-2" dir="ltr">
                    {u.username ? <span className="block font-mono text-xs">@{u.username}</span> : null}
                    {u.email ? <>{u.email} {u.email_verified ? null : <Badge variant="sand">{t('account.emailUnverified')}</Badge>}</> : null}
                    {u.phone ? <span className="block text-xs text-muted-foreground tabular-nums">{u.phone}</span> : null}
                  </td>
                  <td className="px-2 py-2 text-xs text-muted-foreground">{u.created_via}</td>
                  {ROLES.map((r) => (
                    <td key={r} className="px-2 py-2 text-center">
                      <input type="checkbox" checked={pending[`${u.id}:${r}`] ?? u.roles.includes(r)} disabled={`${u.id}:${r}` in pending || (u.id === me.data?.user_id && r === 'administrator')}
                        aria-label={t('account.roleFor', { role: t(`account.role.${r}`), name: u.display_name })}
                        onChange={(e) => {
                          const key = `${u.id}:${r}`;
                          const add = e.target.checked;
                          setPending((p) => ({ ...p, [key]: add }));
                          setRole.mutate({ userId: u.id, role: r, add }, {
                            onSettled: () => void users.refetch().then(() => setPending((p) => {
                              const next = { ...p };
                              delete next[key];
                              return next;
                            })),
                          });
                        }}
                        data-testid={`role-${r}`} className="size-4" />
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
          <ErrorText error={setRole.error} />
        </div>
      )}
    </>
  );
}

// ------------------------------------------------------------------ development mail sink

export function DevMailPage() {
  const { t } = useTranslation();
  const outbox = useDevOutbox();
  const providers = useProviders();
  const smsOutbox = useDevSmsOutbox(providers.data?.sms.status === 'test');
  const linkify = (body: string) =>
    body.split(/(https?:\/\/\S+)/g).map((part, i) =>
      // Links are opened on this origin, whatever address the server put in the message.
      /^https?:\/\//.test(part) ? <a key={i} href={new URL(part).pathname + new URL(part).search} className="break-all text-primary underline">{part}</a> : <span key={i}>{part}</span>);
  return (
    <>
      <PageHeader title={t('account.devMailTitle')} intro={t('account.devMailIntro')} />
      {outbox.isError ? <StatePanel kind="empty"><p className="text-sm text-muted-foreground">{t('account.devMailOff')}</p></StatePanel> : null}
      {providers.data?.sms.status === 'test' ? (
        <section aria-labelledby="dev-sms-heading" className="mb-6 flex flex-col gap-2">
          <h2 id="dev-sms-heading" className="text-lg font-semibold">{t('phone.devSmsTitle')}</h2>
          <p className="text-sm text-muted-foreground">{t('phone.devSmsIntro')}</p>
          <ul className="flex flex-col gap-2" data-testid="dev-sms">
            {smsOutbox.data?.map((m) => (
              <li key={`${m.to}-${m.sent_at}`} className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-border bg-card px-4 py-2 text-sm" data-to={m.to}>
                <span dir="ltr" className="tabular-nums">{m.to}</span>
                <span dir="ltr" className="font-mono text-base tracking-widest" data-testid="dev-sms-code">{m.code}</span>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
      <ul className="flex flex-col gap-3" data-testid="dev-mail">
        {outbox.data?.map((m) => (
          <li key={m.id} className="rounded-lg border border-border bg-card p-4 text-sm" data-purpose={m.purpose} data-to={m.to}>
            <p className="font-semibold" dir="auto">{m.subject}</p>
            <p className="text-xs text-muted-foreground" dir="ltr">{m.to} · {m.created_at.slice(0, 19).replace('T', ' ')}</p>
            <p className="mt-2 whitespace-pre-wrap" dir="auto">{linkify(m.body)}</p>
          </li>
        ))}
      </ul>
    </>
  );
}
