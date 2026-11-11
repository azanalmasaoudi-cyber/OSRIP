import { Copy, KeyRound, UserPlus } from 'lucide-react';
import { useId, useState, type InputHTMLAttributes, type ReactNode } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router';
import { useTranslation } from 'react-i18next';

import {
  hasPermission,
  ROLES,
  useAdminResetPassword,
  useAdminRoles,
  useAdminUsers,
  useChangePassword,
  useLogin,
  useMe,
  useNewRecoveryCode,
  useRecover,
  useRegisterUsername,
  useSetRole,
  useSetUsername,
} from '@/api/auth';
import { ApiRequestError } from '@/api/client';
import { adapterKind } from '@/api/config';
import { GroupsPanel, RolesPanel, useRoleLabel } from '@/components/admin/AccessControl';
import { useDocumentTitle } from '@/lib/useDocumentTitle';
import { normalizeUsername, SIGN_IN_USERNAME_MAX, USERNAME_MAX, usernameProblem, wouldExceed } from '@/lib/username';
import { PageHeader } from '@/components/common/PageHeader';
import { SettingsSection } from '@/components/settings/SettingsSection';
import { StatePanel } from '@/components/common/StatePanel';
import { Button } from '@/components/ui/button';
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

// Server error codes with a translation; anything else shows the server's own message.
const ERROR_CODES = [
  'wrong_current_password', 'weak_password', 'password_unchanged', 'too_many_requests', 'invalid_username',
  'username_required', 'username_too_long', 'username_reserved', 'username_taken', 'password_mismatch',
  'password_contains_username', 'password_too_simple', 'invalid_recovery', 'invalid_credentials', 'too_many_attempts',
  'no_password', 'own_account', 'server_unavailable', 'sign_in_method_retired',
] as const;

function ErrorText({ error, className = 'text-sm text-destructive' }: { error: unknown; className?: string }) {
  const { t } = useTranslation();
  if (!error) return null;
  let message = error instanceof Error ? error.message : t('auth.errors.server_unavailable');
  if (error instanceof ApiRequestError && (ERROR_CODES as readonly string[]).includes(error.code)) {
    const details = (error.details ?? {}) as { minutes?: number };
    message = t(`auth.errors.${error.code as (typeof ERROR_CODES)[number]}`, { minutes: details.minutes ?? 10 });
  }
  return <p role="alert" className={className} data-testid="auth-error">{message}</p>;
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

/** The glass card of the sign-in design (AuthLayout and welcome.css). */
function AuthCard({ title, intro, children, testId }: { title: string; intro?: string; children: ReactNode; testId?: string }) {
  return (
    <div className="ow-box" data-testid={testId}>
      <span aria-hidden="true" className="ow-symbol">O</span>
      <h1 className="ow-heading">{title}</h1>
      {intro ? <p className="ow-intro">{intro}</p> : null}
      {children}
    </div>
  );
}

/** A password field with Show / Hide (named by its text, so "Password" still finds only the field). */
function PasswordField({ label, value, onChange, autoComplete, testId, invalid, revealTestId = `${testId}-reveal` }: {
  label: string; value: string; onChange: (value: string) => void; autoComplete: string; testId: string; invalid?: boolean; revealTestId?: string;
}) {
  const { t } = useTranslation();
  const id = useId();
  const [reveal, setReveal] = useState(false);
  return (
    <div className="ow-field">
      <label htmlFor={id}>{label}</label>
      <div className="ow-field-wrap">
        <input id={id} type={reveal ? 'text' : 'password'} autoComplete={autoComplete} required value={value}
          onChange={(e) => onChange(e.target.value)} dir="ltr" data-testid={testId} aria-invalid={invalid || undefined}
          className="ow-input ow-input-reveal" />
        <button type="button" onClick={() => setReveal((v) => !v)} aria-pressed={reveal} aria-controls={id}
          data-testid={revealTestId} className="ow-show">
          <span aria-hidden="true">{reveal ? t('auth.hide') : t('auth.show')}</span>
          <span className="sr-only">{reveal ? t('auth.hidePassword') : t('auth.showPassword')}</span>
        </button>
      </div>
    </div>
  );
}

/** A new username: at most 10 characters (the field stops there and says so), the rule checked
 * as people type. Arabic names read right to left, English ones left to right (dir="auto"). */
function NewUsernameField({ value, onChange, testId }: { value: string; onChange: (value: string) => void; testId: string }) {
  const { t } = useTranslation();
  const id = useId();
  const hintId = useId();
  const [tooLong, setTooLong] = useState(false);
  const problem = value.trim() ? usernameProblem(value) : null;
  const shown = tooLong ? 'username_too_long' : problem;
  return (
    <div className="ow-field">
      <label htmlFor={id}>{t('account.username')}</label>
      <input id={id} className="ow-input" autoComplete="username" autoCapitalize="none" spellCheck={false} required
        maxLength={USERNAME_MAX} value={value} dir="auto" aria-describedby={hintId} aria-invalid={shown ? true : undefined}
        data-testid={testId}
        onChange={(e) => { onChange(e.target.value); if (e.target.value.length < USERNAME_MAX) setTooLong(false); }}
        onBeforeInput={(e) => {
          const data = e.nativeEvent.data ?? '';
          if (data && wouldExceed(e.currentTarget, data)) setTooLong(true);
        }}
        onPaste={(e) => { if (wouldExceed(e.currentTarget, e.clipboardData.getData('text'))) setTooLong(true); }} />
      {shown ? (
        <p id={hintId} role="alert" className="ow-error" style={{ margin: '6px 0 0' }} data-testid={`${testId}-problem`}>
          {t(`auth.errors.${shown}`)}
        </p>
      ) : (
        <p id={hintId} className="ow-hint">{t('auth.usernameRules', { max: USERNAME_MAX })}</p>
      )}
    </div>
  );
}

// ------------------------------------------------------------------ sign in

/** Sign-in with a username and a password: the only way in (the owner's design: AuthLayout and
 * welcome.css). Older accounts keep their longer usernames, so this field accepts them. */
export function SignInPage() {
  const { t } = useTranslation();
  const login = useLogin();
  const navigate = useNavigate();
  const to = usePreservedSearch();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [remember, setRemember] = useState(false);
  const usernameId = useId();
  const rememberHintId = useId();
  useDocumentTitle(t('auth.title'));

  if (adapterKind !== 'http') return <div className="ow-box"><RequiresApi title={t('auth.title')} /></div>;
  const sectors = ['nav.electricity', 'nav.water', 'nav.foodSecurity', 'nav.trade'] as const;
  const name = normalizeUsername(username);

  return (
    <div className="ow-login" data-testid="sign-in-stage">
      {/* The design's showcase: the name, a line about the platform and the four domains. */}
      <div className="ow-showcase" data-testid="sign-in-showcase">
        <div>
          <p className="ow-showcase-name" lang="en" dir="ltr">OSRIP</p>
          <p className="ow-showcase-caption">{t('welcome.showcaseCaption')}</p>
          <p className="ow-showcase-small">{t('welcome.showcaseSmall')}</p>
        </div>
        <ul className="ow-badges">
          {sectors.map((key) => <li key={key}>{t(key)}</li>)}
        </ul>
      </div>
      <AuthCard title={t('auth.welcome')} intro={t('auth.intro')} testId="sign-in-card">
        <form
          onSubmit={(e) => { e.preventDefault(); login.mutate({ username: name, password, remember }, { onSuccess: () => void navigate(to('/account')) }); }}
          noValidate data-testid="sign-in-form"
        >
          <div className="ow-field">
            <label htmlFor={usernameId}>{t('account.username')}</label>
            <input id={usernameId} className="ow-input" autoComplete="username" autoCapitalize="none" spellCheck={false} required
              maxLength={SIGN_IN_USERNAME_MAX} value={username} onChange={(e) => setUsername(e.target.value)} dir="auto"
              data-testid="sign-in-identifier" />
          </div>
          <PasswordField label={t('auth.password')} value={password} onChange={setPassword} autoComplete="current-password" testId="sign-in-password"
            revealTestId="sign-in-reveal" />
          <div className="ow-row">
            <label className="ow-check">
              <input type="checkbox" checked={remember} onChange={(e) => setRemember(e.target.checked)} aria-describedby={rememberHintId}
                data-testid="sign-in-remember" />
              {t('auth.remember')}
            </label>
            <Link to={to('/forgot-password')} className="ow-link">{t('account.forgot')}</Link>
          </div>
          <p id={rememberHintId} className="ow-hint" style={{ margin: '-10px 0 16px' }}>{t('auth.rememberHint')}</p>
          <ErrorText error={login.error} className="ow-error" />
          <button type="submit" className="ow-primary ow-submit" disabled={login.isPending || !name || !password}>
            {login.isPending ? t('auth.submitting') : t('auth.submit')}<span aria-hidden="true" className="ow-arrow">→</span>
          </button>
        </form>
        <div className="ow-links">
          <Link to={to('/register')} className="ow-link" data-testid="sign-in-register">{t('account.createAccount')}</Link>
        </div>
        {/* The welcome again (AppShell shows it for { welcome: true }), not only once per session. */}
        <button type="button" className="ow-back" onClick={() => void navigate(to('/'), { state: { welcome: true } })} data-testid="sign-in-back">
          <span aria-hidden="true" className="ow-arrow">←</span> {t('auth.backToIntro')}
        </button>
      </AuthCard>
    </div>
  );
}

/** The recovery code, shown once: copy it, confirm it was saved, then continue. */
function RecoveryCodePanel({ code, onContinue, glass = false }: { code: string; onContinue: () => void; glass?: boolean }) {
  const { t } = useTranslation();
  const [saved, setSaved] = useState(false);
  const [copied, setCopied] = useState(false);
  const copy = () => { void navigator.clipboard?.writeText(code).then(() => setCopied(true), () => setCopied(false)); };
  return (
    <div className="flex flex-col gap-4" data-testid="recovery-panel">
      <p className={glass ? 'ow-notice' : 'text-base'}>{t('account.recoveryShownOnce')}</p>
      <p className="rounded-md border border-sand/60 bg-sand-subtle px-4 py-3 text-center font-mono text-xl tracking-wider text-sand-foreground select-all"
        dir="ltr" data-testid="recovery-code">{code}</p>
      {glass ? (
        <button type="button" className="ow-secondary" onClick={copy} data-testid="recovery-copy">
          <Copy aria-hidden="true" className="size-4" />{copied ? t('account.recoveryCopied') : t('account.recoveryCopy')}
        </button>
      ) : (
        <Button type="button" variant="outline" className="w-fit" data-testid="recovery-copy" onClick={copy}>
          <Copy aria-hidden="true" />{copied ? t('account.recoveryCopied') : t('account.recoveryCopy')}
        </Button>
      )}
      <label className={glass ? 'ow-check' : 'flex items-start gap-2 text-base'}>
        <input type="checkbox" checked={saved} onChange={(e) => setSaved(e.target.checked)} className={glass ? undefined : 'mt-1 size-4 accent-primary'}
          data-testid="recovery-saved" />
        {t('account.recoverySaved')}
      </label>
      {glass ? (
        <button type="button" className="ow-primary ow-submit" disabled={!saved} onClick={onContinue} data-testid="recovery-continue">
          {t('account.recoveryContinue')}<span aria-hidden="true" className="ow-arrow">→</span>
        </button>
      ) : (
        <Button type="button" className="w-fit" disabled={!saved} onClick={onContinue} data-testid="recovery-continue">
          {t('account.recoveryContinue')}
        </Button>
      )}
    </div>
  );
}

// ------------------------------------------------------------------ register

/** Registration: a username, a password and the password again. Nothing else is asked; the
 * account is an ordinary (viewer) one, whatever is sent. */
export function RegisterPage() {
  const { t } = useTranslation();
  const register = useRegisterUsername();
  const to = usePreservedSearch();
  const navigate = useNavigate();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  useDocumentTitle(t('account.registerTitle'));

  if (adapterKind !== 'http') return <div className="ow-box"><RequiresApi title={t('account.registerTitle')} /></div>;
  if (register.data) {
    return (
      <AuthCard title={t('account.registeredTitle')} testId="register-done">
        <RecoveryCodePanel glass code={register.data.recovery_code} onContinue={() => void navigate(to('/account'))} />
      </AuthCard>
    );
  }
  const name = normalizeUsername(username);
  const mismatch = confirm.length > 0 && confirm !== password;
  return (
    <AuthCard title={t('account.registerTitle')} testId="register-card">
      <form onSubmit={(e) => { e.preventDefault(); register.mutate({ username: name, password, password_confirm: confirm }); }}
        noValidate data-testid="register-form">
        <NewUsernameField value={username} onChange={setUsername} testId="register-username" />
        <PasswordField label={t('auth.password')} value={password} onChange={setPassword} autoComplete="new-password" testId="register-password" />
        <PasswordField label={t('auth.confirmPassword')} value={confirm} onChange={setConfirm} autoComplete="new-password"
          testId="register-confirm" invalid={mismatch} />
        {mismatch ? <p className="ow-error" role="alert" data-testid="register-mismatch">{t('auth.errors.password_mismatch')}</p> : null}
        <p className="ow-hint" style={{ margin: '-8px 0 16px' }}>{t('account.passwordHint')}</p>
        <ErrorText error={register.error} className="ow-error" />
        <button type="submit" className="ow-primary ow-submit" data-testid="register-submit"
          disabled={register.isPending || usernameProblem(username) !== null || password.length < 12 || confirm !== password}>
          <UserPlus aria-hidden="true" className="size-4" />{t('account.createAccount')}
        </button>
      </form>
      <div className="ow-links">
        <Link to={to('/sign-in')} className="ow-link">{t('account.haveAccount')}</Link>
      </div>
    </AuthCard>
  );
}

// ------------------------------------------------------------------ forgotten password

/** A forgotten password: the username, the recovery code and a new password. Without the code an
 * administrator resets the password; knowing a username alone never resets anything. */
export function ForgotPasswordPage() {
  const { t } = useTranslation();
  const recover = useRecover();
  const navigate = useNavigate();
  const to = usePreservedSearch();
  const [username, setUsername] = useState('');
  const [code, setCode] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const usernameId = useId();
  const codeId = useId();
  useDocumentTitle(t('account.forgotTitle'));

  if (adapterKind !== 'http') return <div className="ow-box"><RequiresApi title={t('account.forgotTitle')} /></div>;
  if (recover.data) {
    return (
      <AuthCard title={t('account.recoveredTitle')} intro={t('account.recoveredNotice')} testId="recover-done">
        <RecoveryCodePanel glass code={recover.data.recovery_code} onContinue={() => void navigate(to('/account'))} />
      </AuthCard>
    );
  }
  const mismatch = confirm.length > 0 && confirm !== password;
  const name = normalizeUsername(username);
  return (
    <AuthCard title={t('account.forgotTitle')} intro={t('account.forgotIntro')} testId="recover-card">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          recover.mutate({ username: name, recovery_code: code, new_password: password, new_password_confirm: confirm });
        }}
        noValidate data-testid="recover-form"
      >
        <div className="ow-field">
          <label htmlFor={usernameId}>{t('account.username')}</label>
          <input id={usernameId} className="ow-input" autoComplete="username" autoCapitalize="none" spellCheck={false} required
            maxLength={SIGN_IN_USERNAME_MAX} value={username} onChange={(e) => setUsername(e.target.value)} dir="auto" data-testid="recover-username" />
        </div>
        <div className="ow-field">
          <label htmlFor={codeId}>{t('account.recoveryCodeLabel')}</label>
          <input id={codeId} className="ow-input" autoComplete="off" autoCapitalize="characters" spellCheck={false} required
            value={code} onChange={(e) => setCode(e.target.value)} dir="ltr" placeholder="ABCD-EFGH-JKMN-PQRS-TWXY" data-testid="recover-code" />
        </div>
        <PasswordField label={t('account.newPassword')} value={password} onChange={setPassword} autoComplete="new-password" testId="recover-password" />
        <PasswordField label={t('auth.confirmPassword')} value={confirm} onChange={setConfirm} autoComplete="new-password"
          testId="recover-confirm" invalid={mismatch} />
        {mismatch ? <p className="ow-error" role="alert">{t('auth.errors.password_mismatch')}</p> : null}
        <ErrorText error={recover.error} className="ow-error" />
        <button type="submit" className="ow-primary ow-submit" data-testid="recover-submit"
          disabled={recover.isPending || !name || !code.trim() || password.length < 12 || confirm !== password}>
          <KeyRound aria-hidden="true" className="size-4" />{t('account.recoverSubmit')}
        </button>
      </form>
      <p className="ow-fine">{t('account.noRecoveryCode')}</p>
      <div className="ow-links">
        <Link to={to('/sign-in')} className="ow-link">{t('auth.backToSignIn')}</Link>
      </div>
    </AuthCard>
  );
}

// ------------------------------------------------------------------ account

export function AccountPage() {
  const { t } = useTranslation();
  const me = useMe();
  const to = usePreservedSearch();

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
        <Card className="p-5">
          <dl className="grid gap-x-4 gap-y-2 text-sm sm:grid-cols-[auto_1fr]">
            <dt className="text-muted-foreground">{t('account.name')}</dt><dd>{me.data.display_name}</dd>
            <dt className="text-muted-foreground">{t('account.username')}</dt>
            <dd dir="auto" data-testid="account-username">{me.data.username ?? '—'}</dd>
            <dt className="text-muted-foreground">{t('account.roles')}</dt>
            <dd data-testid="account-roles">{me.data.roles.map((r) => t(`account.role.${r as 'viewer'}`)).join(document.documentElement.lang === 'ar' ? '، ' : ', ') || '—'}</dd>
          </dl>
          <p className="mt-3 text-xs text-muted-foreground">{t('account.rolesNote')}</p>
        </Card>
        {me.data.has_password ? <ChangePassword /> : null}
        {me.data.has_password ? <RecoveryCodeSection has={me.data.has_recovery_code === true} /> : null}
        <SettingsSection />
      </div>
    </>
  );
}

/** A new recovery code (the current password first); the old code stops working. */
function RecoveryCodeSection({ has }: { has: boolean }) {
  const { t } = useTranslation();
  const create = useNewRecoveryCode();
  const [current, setCurrent] = useState('');
  return (
    <section aria-labelledby="recovery-section-heading" className="surface-card flex flex-col gap-3 p-5" data-testid="recovery-section">
      <h2 id="recovery-section-heading" className="text-lg font-semibold">{t('account.recoverySectionTitle')}</h2>
      {create.data ? (
        <RecoveryCodePanel code={create.data.recovery_code} onContinue={() => create.reset()} />
      ) : (
        <>
          <p className="text-base text-muted-foreground" data-testid="recovery-status">{has ? t('account.recoveryHas') : t('account.recoveryNone')}</p>
          <form onSubmit={(e) => { e.preventDefault(); create.mutate(current, { onSuccess: () => setCurrent('') }); }}
            className="flex flex-col gap-3" noValidate>
            <Field label={t('account.currentPassword')} type="password" autoComplete="current-password" value={current}
              onChange={(e) => setCurrent(e.target.value)} dir="ltr" data-testid="recovery-current-password" />
            <ErrorText error={create.error} />
            <Button type="submit" variant="outline" className="w-fit" disabled={create.isPending || !current} data-testid="recovery-new">
              <KeyRound aria-hidden="true" />{t('account.recoveryNew')}
            </Button>
          </form>
        </>
      )}
    </section>
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

// ------------------------------------------------------------------ administration

/** The tab of the users page, kept in ?tab= (replaced, not pushed). */
function useTabParam<T extends string>(values: readonly T[], fallback: T): [T, (value: T) => void] {
  const [params, setParams] = useSearchParams();
  const value = values.find((v) => v === params.get('tab')) ?? fallback;
  const set = (next: T) => setParams((prev) => {
    const updated = new URLSearchParams(prev);
    if (next === fallback) updated.delete('tab'); else updated.set('tab', next);
    return updated;
  }, { replace: true });
  return [value, set];
}

/** An account without a username (it used an e-mail address or a phone number before those were
 * retired) gets one here; the administrator can then hand over a temporary password. */
function AssignUsername({ userId, name }: { userId: string; name: string }) {
  const { t } = useTranslation();
  const assign = useSetUsername();
  const [value, setValue] = useState('');
  const problem = value.trim() ? usernameProblem(value) : null;
  return (
    <form className="flex flex-wrap items-center gap-1" noValidate data-testid="assign-username"
      onSubmit={(e) => { e.preventDefault(); assign.mutate({ userId, username: normalizeUsername(value) }, { onSuccess: () => setValue('') }); }}>
      <input value={value} onChange={(e) => setValue(e.target.value)} maxLength={USERNAME_MAX} dir="auto"
        aria-label={t('account.assignUsernameFor', { name })} placeholder={t('account.assignUsername')}
        className="h-8 w-28 rounded-md border border-border-strong bg-card px-2 text-xs" data-testid="assign-username-input" />
      <Button type="submit" size="sm" variant="outline" disabled={assign.isPending || !value.trim() || problem !== null}
        data-testid="assign-username-save">{t('account.assignUsernameSave')}</Button>
      {problem ? <span className="w-full text-xs text-destructive">{t(`auth.errors.${problem}`)}</span> : null}
      <ErrorText error={assign.error} className="w-full text-xs text-destructive" />
    </form>
  );
}

export function AdminUsersPage() {
  const { t } = useTranslation();
  const me = useMe();
  const allowed = hasPermission(me.data, 'user.manage');
  const [tab, setTab] = useTabParam(['users', 'roles', 'groups'] as const, 'users');
  const users = useAdminUsers(adapterKind === 'http' && allowed);
  const roleList = useAdminRoles(adapterKind === 'http' && allowed);
  const roleLabel = useRoleLabel();
  // Built-in and custom roles, as the server lists them.
  const roleCodes: readonly string[] = roleList.data?.map((r) => r.code) ?? ROLES;
  const setRole = useSetRole();
  const reset = useAdminResetPassword();
  const [confirmReset, setConfirmReset] = useState<string | null>(null);
  const [temporary, setTemporary] = useState<{ name: string; password: string } | null>(null);
  // Optimistic state per checkbox until the server answers; the list is refetched afterwards.
  const [pending, setPending] = useState<Record<string, boolean>>({});

  if (adapterKind !== 'http') return <RequiresApi title={t('account.adminTitle')} />;
  return (
    <>
      <PageHeader title={t('account.adminTitle')} intro={t('account.adminIntro')} />
      {allowed ? (
        <Segmented label={t('access.title')} value={tab} onChange={setTab} testId="access-tabs" className="mb-5" options={[
          { value: 'users', label: t('access.tabUsers') },
          { value: 'roles', label: t('access.tabRoles') },
          { value: 'groups', label: t('access.tabGroups') },
        ]} />
      ) : null}
      {allowed && tab === 'roles' ? <RolesPanel /> : allowed && tab === 'groups' ? <GroupsPanel /> : !allowed ? <StatePanel kind="restricted" /> : users.isPending ? <StatePanel kind="loading" skeleton="lines" /> : users.isError ? (
        <StatePanel kind="error" detail={users.error.message} onRetry={() => void users.refetch()} />
      ) : (
        <div className="relative overflow-x-auto rounded-lg border border-border bg-card">
          <table className="w-full min-w-[44rem] text-sm" data-testid="admin-users">
            <caption className="px-4 pt-3 text-start text-xs text-muted-foreground">{t('account.adminCaption')}</caption>
            <thead>
              <tr className="border-b border-border-strong/40 text-xs text-muted-foreground">
                <th scope="col" className="px-4 py-2 text-start font-medium">{t('account.name')}</th>
                <th scope="col" className="px-2 py-2 text-start font-medium">{t('account.username')}</th>
                <th scope="col" className="px-2 py-2 text-start font-medium">{t('account.createdVia')}</th>
                {roleCodes.map((r) => <th key={r} scope="col" className="px-2 py-2 text-center font-medium">{roleLabel(r)}</th>)}
                <th scope="col" className="px-2 py-2 text-start font-medium">{t('account.adminPassword')}</th>
              </tr>
            </thead>
            <tbody>
              {users.data.map((u) => (
                <tr key={u.id} className="border-b border-border last:border-0" data-username={u.username ?? undefined} data-user-id={u.id}>
                  <th scope="row" className="px-4 py-2 text-start font-medium">{u.display_name}</th>
                  <td className="px-2 py-2">
                    {u.username ? <span className="block font-mono text-xs" dir="auto">{u.username}</span>
                      : u.service_account ? <span className="block text-xs text-muted-foreground">{t('account.serviceAccount')}</span>
                        : <AssignUsername userId={u.id} name={u.display_name} />}
                    {/* Kept as records only: they no longer sign anyone in. */}
                    {u.email ? <span className="block text-xs text-muted-foreground" dir="ltr">{u.email}</span> : null}
                    {u.phone ? <span className="block text-xs text-muted-foreground tabular-nums" dir="ltr">{u.phone}</span> : null}
                  </td>
                  <td className="px-2 py-2 text-xs text-muted-foreground">{u.created_via}</td>
                  {roleCodes.map((r) => (
                    <td key={r} className="px-2 py-2 text-center">
                      <input type="checkbox" checked={pending[`${u.id}:${r}`] ?? u.roles.includes(r)} disabled={`${u.id}:${r}` in pending || (u.id === me.data?.user_id && r === 'administrator')}
                        aria-label={t('account.roleFor', { role: roleLabel(r), name: u.display_name })}
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
                  <td className="px-2 py-2">
                    {u.id === me.data?.user_id ? null : confirmReset === u.id ? (
                      <span className="flex flex-wrap gap-1">
                        <Button size="sm" variant="outline" disabled={reset.isPending} data-testid="reset-password-confirm"
                          onClick={() => reset.mutate(u.id, {
                            onSuccess: (r) => setTemporary({ name: u.display_name, password: r.temporary_password }),
                            onSettled: () => setConfirmReset(null),
                          })}>
                          {t('account.adminResetConfirm')}
                        </Button>
                        <Button size="sm" variant="ghost" onClick={() => setConfirmReset(null)}>{t('account.adminResetCancel')}</Button>
                      </span>
                    ) : (
                      <Button size="sm" variant="outline" data-testid="reset-password" onClick={() => { setConfirmReset(u.id); setTemporary(null); }}>
                        {t('account.adminReset')}
                      </Button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <ErrorText error={setRole.error} />
          <ErrorText error={reset.error} />
          {temporary ? (
            <div className="m-4"><Notice tone="success">
              <span className="block">{t('account.adminResetDone', { name: temporary.name })}</span>
              <code className="mt-2 block font-mono text-lg" dir="ltr" data-testid="temporary-password">{temporary.password}</code>
            </Notice></div>
          ) : null}
        </div>
      )}
    </>
  );
}
