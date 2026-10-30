'use client';

import { useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { authApi, residentApi } from '@/lib/endpoints';
import { useAuth } from '@/components/auth-provider';
import { Alert, Button, Field } from '@/components/ui';
import { PublicShell, AuthCard } from '@/components/shell';
import { Icon } from '@/components/icons';
import { errorText } from '@/lib/use-load';
import { ApiError } from '@/lib/api';
import {hasPendingInvitation} from '@/lib/invitation-handoff';
import {destinationAfterLogin} from '@/lib/login-routing';
import {
  FIELD_NAMES,
  PASSWORD_MAX_LENGTH,
  PASSWORD_MIN_LENGTH,
  errorSummary,
  normalizeAuthFieldErrors,
  validateAuthForm,
  type AuthFieldErrors,
  type AuthFields,
  type AuthFormMode,
} from './validation';

type Mode = AuthFormMode;

const titles: Record<Mode, [string, string, string]> = {
  login: ['RESIDENT ACCESS', 'Welcome back', 'Sign in to your Green Valley community account.'],
  register: ['JOIN YOUR COMMUNITY', 'Create your account', 'Start with a secure account. Residency is verified separately.'],
  forgot: ['ACCOUNT RECOVERY', 'Forgot your password?', 'We will email a reset link if an eligible account exists.'],
  'check-inbox': ['EMAIL VERIFICATION', 'Check your inbox', 'Open the secure link sent to your email to verify your account.'],
  verify: ['CONFIRM YOUR EMAIL', 'Verify your email', 'Complete your account verification to continue.'],
  reset: ['ACCOUNT RECOVERY', 'Choose a new password', 'Reset links are valid for 30 minutes and can be used once.'],
};

function consumeTokenFromUrl() {
  const url = new URL(window.location.href);
  const token = url.searchParams.get('token') ?? '';
  if (token) {
    url.searchParams.delete('token');
    window.history.replaceState({}, '', url.pathname + url.search + url.hash);
  }
  return token;
}

function focusFirstInvalidField(fields: AuthFieldErrors) {
  const first = Object.keys(fields)[0] as AuthFields | undefined;
  if (!first) return;
  const id = first === 'display_name' ? 'name' : first;
  document.getElementById(id)?.focus();
}

export function AuthScreen({ mode }: { mode: Mode }) {
  const router = useRouter();
  const session = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [displayName, setDisplayName] = useState('');
  const [phone, setPhone] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [registered, setRegistered] = useState(false);
  const [showPass, setShowPass] = useState(false);
  const [token, setToken] = useState('');
  const [fieldErrors, setFieldErrors] = useState<AuthFieldErrors>({});
  const [extraErrors, setExtraErrors] = useState<string[]>([]);
  const [hasInvite, setHasInvite] = useState(false);
  const initialized = useRef(false);

  useEffect(() => {
    if (initialized.current) return;
    initialized.current = true;
    if (mode === 'verify' || mode === 'reset') {
      void Promise.resolve().then(() => setToken(consumeTokenFromUrl()));
    }
  }, [mode]);

  useEffect(() => {void Promise.resolve().then(() => setHasInvite(hasPendingInvitation()));}, []);

  const [eyebrow, title, subtitle] = titles[mode];

  // Keep other field errors visible, but clear a field's old error as it is edited.
  function edited(field: AuthFields, value: string, update: (value: string) => void) {
    update(value);
    setError('');
    setExtraErrors([]);
    setFieldErrors(previous => {
      if (!previous[field]) return previous;
      const next = { ...previous };
      delete next[field];
      return next;
    });
  }

  function presentFailure(failure: unknown) {
    if (!(failure instanceof ApiError)) {
      setError(errorText(failure));
      return;
    }

    const parsed = normalizeAuthFieldErrors(failure.fields);
    setFieldErrors(parsed.fields);
    setExtraErrors(parsed.extra);
    setError(errorSummary(failure.status, failure.code, mode,
      Object.keys(parsed.fields).length > 0 || parsed.extra.length > 0) || failure.message);
    focusFirstInvalidField(parsed.fields);
  }

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    setError('');
    setSuccess('');
    setFieldErrors({});
    setExtraErrors([]);

    const errors = validateAuthForm(mode, {
      display_name: displayName,
      phone,
      email,
      password,
      confirm,
    });
    if (Object.keys(errors).length > 0) {
      setFieldErrors(errors);
      setError('Please correct the highlighted fields below.');
      focusFirstInvalidField(errors);
      return;
    }

    if ((mode === 'verify' || mode === 'reset') && !token) {
      setError(mode === 'verify'
        ? 'The verification link is missing or has already been used in this tab. Request a fresh email.'
        : 'The reset link is missing or has already been used in this tab. Request a fresh reset link.');
      return;
    }

    setBusy(true);
    try {
      if (mode === 'login') {
        const { user } = await authApi.login({ email: email.trim(), password });
        await session.signedIn(user);
        const access = await residentApi.access();
        // Ignore stale ?next= URLs, including admin routes from a previous account.
        // The only supported return flow is a deliberate invitation handoff.
        const hasInviteHandoff = hasPendingInvitation();
        router.replace(user.email_verified
          ? destinationAfterLogin(access.roles, hasInviteHandoff)
          : (hasInviteHandoff?'/check-inbox?next=%2Finvitations%2Faccept':'/check-inbox'));
      } else if (mode === 'register') {
        await authApi.register({
          display_name: displayName.trim(),
          email: email.trim(),
          password,
          phone: phone.trim() || null,
        });
        setRegistered(true);
        setPassword('');
        setConfirm('');
      } else if (mode === 'forgot') {
        await authApi.forgot(email.trim());
        setSuccess('If an eligible account exists, a password-reset link will be sent. Check your inbox and spam folder.');
      } else if (mode === 'check-inbox') {
        await authApi.resend(email.trim());
        setSuccess('If the account is eligible, a new verification link has been sent.');
      } else if (mode === 'verify') {
        await authApi.verify(token);
        setToken('');
        setSuccess('Email verified successfully. Sign in to finish accepting your pending invitation, if you have one.');
      } else if (mode === 'reset') {
        await authApi.reset(token, password);
        setToken('');
        setPassword('');
        setConfirm('');
        await session.refresh();
        setSuccess('Your password has been changed. Existing sessions were revoked. Please sign in again.');
      }
    } catch (failure) {
      presentFailure(failure);
    } finally {
      setBusy(false);
    }
  }

  if (registered) {
    return <PublicShell><AuthCard
      eyebrow="REGISTRATION RECEIVED"
      title="Check your inbox"
      subtitle="Your account was created as an unverified applicant. Residency is not yet approved."
    >
      <div className="mb-6 flex justify-center">
        <div className="empty-icon" style={{ width: 76, height: 76 }}><Icon name="mail" size={32} /></div>
      </div>
      <Alert tone="success">A verification email has been requested for <strong>{email}</strong>. Follow its link within 24 hours. Check spam if necessary.</Alert>
      <div className="form-actions">
        <Button variant="secondary" busy={busy} onClick={async () => {
          setError(''); setSuccess(''); setBusy(true);
          try {
            await authApi.resend(email);
            setSuccess('A new email has been requested.');
          } catch (failure) {
            presentFailure(failure);
          } finally {
            setBusy(false);
          }
        }}>Resend verification</Button>
        <Link href={hasInvite?"/login?next=%2Finvitations%2Faccept":"/login"} className="btn btn-primary">Go to sign in</Link>
      </div>
      {error && <div className="mt-4"><Alert tone="danger">{error}</Alert></div>}
      {success && <div className="mt-4"><Alert tone="success">{success}</Alert></div>}
    </AuthCard></PublicShell>;
  }

  const fieldList = (Object.entries(fieldErrors) as [AuthFields, string][]);

  return <PublicShell><AuthCard eyebrow={eyebrow} title={title} subtitle={subtitle}>
    {error && <div className="mb-5"><Alert tone="danger">
      <div>
        <p className="font-semibold">{error}</p>
        {(fieldList.length > 0 || extraErrors.length > 0) && <ul className="mt-2 list-disc space-y-1 pl-4">
          {fieldList.map(([field, message]) => <li key={field}><strong>{FIELD_NAMES[field]}:</strong> {message}</li>)}
          {extraErrors.map((message, index) => <li key={index}>{message}</li>)}
        </ul>}
        {mode === 'register' && error.includes('already exists') && <Link className="mt-2 inline-block underline" href="/login">Sign in instead</Link>}
      </div>
    </Alert></div>}
    {success && <div className="mb-5"><Alert tone="success">{success}</Alert></div>}

    <form onSubmit={submit} className="form-stack" noValidate>
      {mode === 'register' && <>
        <Field id="name" error={fieldErrors.display_name} label="Full name"
          value={displayName} onChange={e => edited('display_name', e.target.value, setDisplayName)}
          required minLength={2} maxLength={120} autoComplete="name" placeholder="Your full name" />
        <Field id="phone" error={fieldErrors.phone} label="Phone (optional)" type="tel"
          value={phone} onChange={e => edited('phone', e.target.value, setPhone)}
          autoComplete="tel" placeholder="Your contact number" />
      </>}

      {(['login', 'register', 'forgot', 'check-inbox'] as Mode[]).includes(mode) &&
        <Field id="email" error={fieldErrors.email} type="email" label="Email address"
          autoComplete="email" value={email}
          onChange={e => edited('email', e.target.value, setEmail)}
          placeholder="you@example.com" required />}

      {(['login', 'register', 'reset'] as Mode[]).includes(mode) &&
        <div className="field">
          <label className="between" htmlFor="password">
            <span className="field-title">{mode === 'reset' ? 'New password' : 'Password'}</span>
            {mode === 'login' && <Link className="text-link small" href="/forgot-password">Forgot password?</Link>}
          </label>
          <span className="relative">
            <input id="password" type={showPass ? 'text' : 'password'}
              className={`input pr-12 ${fieldErrors.password ? 'input-error' : ''}`}
              aria-invalid={Boolean(fieldErrors.password)}
              aria-describedby={fieldErrors.password ? 'password-error' : mode !== 'login' ? 'password-hint' : undefined}
              value={password} onChange={e => edited('password', e.target.value, setPassword)}
              required minLength={mode === 'login' ? undefined : PASSWORD_MIN_LENGTH}
              maxLength={mode === 'login' ? undefined : PASSWORD_MAX_LENGTH}
              autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
              placeholder="Enter your password" />
            <button type="button" aria-label={showPass ? 'Hide password' : 'Show password'}
              onClick={() => setShowPass(current => !current)}
              className="absolute right-3 top-3 text-slate-500"><Icon name="eye" size={18} /></button>
          </span>
          {mode !== 'login' && <span className="hint" id="password-hint">
            Use {PASSWORD_MIN_LENGTH}–{PASSWORD_MAX_LENGTH} characters.
          </span>}
          {fieldErrors.password && <span id="password-error" className="field-error" role="alert">{fieldErrors.password}</span>}
        </div>}

      {(mode === 'register' || mode === 'reset') &&
        <Field id="confirm" error={fieldErrors.confirm} label="Confirm password" type="password"
          value={confirm} onChange={e => edited('confirm', e.target.value, setConfirm)}
          autoComplete="new-password" required placeholder="Repeat your password" />}

      {mode === 'verify' && <Alert tone="info">{token
        ? 'Your verification link is ready. Select Verify email to confirm your address.'
        : 'No verification token was found in this URL. Request a fresh link using the resend page.'}</Alert>}
      {mode === 'reset' && !token && <Alert tone="warning">
        The reset token is missing or has already been used in this browser tab.
      </Alert>}

      <Button type="submit" busy={busy} disabled={(mode === 'verify' || mode === 'reset') && !token} className="w-full">
        {mode === 'login' ? 'Sign in'
          : mode === 'register' ? 'Create account'
          : mode === 'forgot' ? 'Send reset link'
          : mode === 'check-inbox' ? 'Resend verification link'
          : mode === 'verify' ? 'Verify email' : 'Reset password'}
        <Icon name="arrow" size={16} />
      </Button>
    </form>

    <div className="auth-footer-text">
      {mode === 'login' ? <>New to KNOWALL? <Link href={hasInvite?"/register?next=%2Finvitations%2Faccept":"/register"}>Create an account</Link></>
        : mode === 'register' ? <>Already registered? <Link href={hasInvite?"/login?next=%2Finvitations%2Faccept":"/login"}>Sign in</Link></>
        : <>Return to <Link href={hasInvite?"/login?next=%2Finvitations%2Faccept":"/login"}>sign in</Link>
            {mode === 'verify' && <> · <Link href="/check-inbox">Resend email</Link></>}
            {mode === 'reset' && <> · <Link href="/forgot-password">Request new link</Link></>}
          </>}
    </div>
    <div className="mt-8 border-t border-slate-200 pt-5 flex items-center gap-3 text-slate-400 text-xs">
      <Icon name="lock" size={16} /><span>Session security is managed by KNOWALL Flask backend.</span>
    </div>
  </AuthCard></PublicShell>;
}
