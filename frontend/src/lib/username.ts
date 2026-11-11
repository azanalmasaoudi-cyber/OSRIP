/**
 * The username rule, as the server applies it (backend app/services/usernames.py): 1 to 10
 * Arabic or English letters and digits, starting with a letter; `_`, `.` and `-` may be used.
 * Checked as people type so the form can say what is wrong; the server decides.
 */

export const USERNAME_MAX = 10;
/** Sign-in also accepts the longer usernames some accounts had before the rule. */
export const SIGN_IN_USERNAME_MAX = 64;

const ARABIC = 'ء-غف-يٮٯٱ-ۓ';
const PATTERN = new RegExp(`^(?:[A-Za-z][A-Za-z0-9_.-]*|[${ARABIC}][${ARABIC}0-9_.-]*)$`);
const ARABIC_DIGITS = /[٠-٩۰-۹]/g;

/** As the server stores it: NFKC, Arabic-Indic digits as 0-9, no surrounding spaces. */
export function normalizeUsername(raw: string): string {
  return raw
    .normalize('NFKC')
    .replace(ARABIC_DIGITS, (d) => String((d.charCodeAt(0) & 0xf) % 10))
    .trim();
}

export type UsernameProblem = 'username_required' | 'username_too_long' | 'invalid_username';

export function usernameProblem(raw: string): UsernameProblem | null {
  const name = normalizeUsername(raw);
  if (!name) return 'username_required';
  if ([...name].length > USERNAME_MAX) return 'username_too_long';
  return PATTERN.test(name) ? null : 'invalid_username';
}

/** Whether typing or pasting `inserted` into the field would go past the limit (the field's
 * maxLength then stops it, and the page says why). */
export function wouldExceed(input: HTMLInputElement, inserted: string): boolean {
  const selected = (input.selectionEnd ?? 0) - (input.selectionStart ?? 0);
  return input.value.length - selected + inserted.length > USERNAME_MAX;
}
