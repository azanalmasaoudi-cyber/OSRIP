import type { ReactElement } from 'react';

import { StatePanel } from './StatePanel';

interface MeQuery {
  isPending: boolean;
  isError: boolean;
  error: unknown;
  data?: { authenticated: boolean } | undefined;
  refetch: () => unknown;
}

/**
 * What a protected page shows while it cannot yet decide about access: the account check still
 * running, the check failing (the server not connected or not responding: said so, with Retry,
 * never shown as "authorized access only"), or nobody signed in (a Sign-in link). Null once a
 * signed-in account is known; the page then checks its permission itself.
 */
export function accessPanel(me: MeQuery): ReactElement | null {
  if (me.isPending) return <StatePanel kind="loading" skeleton="lines" />;
  if (me.isError) return <StatePanel kind="error" error={me.error} onRetry={() => void me.refetch()} />;
  if (!me.data?.authenticated) return <StatePanel kind="sign_in_required" />;
  return null;
}
