/** Frontend validation aligned with the KNOWALL Flask authentication contract.
 * Flask remains authoritative; these checks are for immediate user feedback.
 */
export type AuthFormMode = 'login' | 'register' | 'forgot' | 'check-inbox' | 'verify' | 'reset';
export type AuthFields = 'display_name' | 'phone' | 'email' | 'password' | 'confirm';
export type AuthFieldErrors = Partial<Record<AuthFields, string>>;

export interface AuthFormValues {
  display_name: string;
  phone: string;
  email: string;
  password: string;
  confirm: string;
}

export const FIELD_NAMES: Record<AuthFields, string> = {
  display_name: 'Full name',
  phone: 'Phone',
  email: 'Email address',
  password: 'Password',
  confirm: 'Confirm password',
};

export const PASSWORD_MIN_LENGTH = 12;
export const PASSWORD_MAX_LENGTH = 128;

export function validateAuthForm(mode: AuthFormMode, values: AuthFormValues): AuthFieldErrors {
  const errors: AuthFieldErrors = {};

  if (mode === 'register') {
    const name = values.display_name.trim();
    if (name.length < 2 || name.length > 120) {
      errors.display_name = 'Enter your full name (2–120 characters).';
    }
  }

  if (['login', 'register', 'forgot', 'check-inbox'].includes(mode)) {
    const email = values.email.trim();
    if (!email) errors.email = 'Enter your email address.';
    else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
      errors.email = 'Enter a valid email address, such as name@example.com.';
    }
  }

  if (mode === 'login' && !values.password) {
    errors.password = 'Enter your password.';
  }

  if (mode === 'register' || mode === 'reset') {
    if (values.password.length < PASSWORD_MIN_LENGTH || values.password.length > PASSWORD_MAX_LENGTH) {
      errors.password = `Use a password between ${PASSWORD_MIN_LENGTH} and ${PASSWORD_MAX_LENGTH} characters.`;
    }
    if (!values.confirm) errors.confirm = 'Confirm your password.';
    else if (values.password !== values.confirm) {
      errors.confirm = 'Passwords do not match. Re-enter the confirmation.';
    }
  }

  // Phone is optional; defer format rules to the Flask backend rather than inventing them.
  return errors;
}

/** Flask may use `new_password` for reset; the visible form always uses `password`. */
export function normalizeAuthFieldErrors(
  serverFields: Record<string, string> = {},
): { fields: AuthFieldErrors; extra: string[] } {
  const fields: AuthFieldErrors = {};
  const extra: string[] = [];
  const known = new Set<AuthFields>(['display_name', 'phone', 'email', 'password', 'confirm']);

  for (const [key, message] of Object.entries(serverFields)) {
    if (typeof message !== 'string' || !message.trim()) continue;
    const normalizedKey = key === 'new_password' ? 'password' : key;
    if (known.has(normalizedKey as AuthFields)) {
      fields[normalizedKey as AuthFields] = message;
    } else {
      // Unknown fields still get shown in the summary rather than silently discarded.
      const readable = key.replaceAll('_', ' ');
      extra.push(`${readable}: ${message}`);
    }
  }
  return { fields, extra };
}

export function errorSummary(status: number, code: string, mode: AuthFormMode, hasFields: boolean): string {
  if (code === 'CSRF_REQUIRED') return 'Your secure form session expired. Please submit the form again.';
  if (code === 'EMAIL_ALREADY_REGISTERED' && mode === 'register') {
    return 'An account already exists with this email. Sign in or use Forgot password.';
  }
  if (code === 'INVALID_OR_EXPIRED_TOKEN') {
    return 'This link is invalid, expired, or has already been used. Request a new link.';
  }
  if (code === 'PASSWORD_REUSE_NOT_ALLOWED') return 'Choose a new password that you have not used for this account.';
  if (status === 429) return 'Too many attempts. Please try again later.';
  if (status === 503) return 'The service is temporarily unavailable. Please try again later.';
  if (status === 0 || code === 'NETWORK') return 'Cannot reach the server. Check your connection and make sure Flask is running.';
  if (status === 401 && mode === 'login') return 'Could not sign in. Check your email and password.';
  if (hasFields) return 'Please correct the highlighted fields below.';
  if (status === 400 && code === 'VALIDATION_ERROR') {
    return 'The server rejected the submitted details but did not identify a field. Review your entries and try again.';
  }
  return '';
}
