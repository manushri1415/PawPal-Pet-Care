import './Session.css';
import type { ReactNode } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { ApiError } from '../../api/client';
import { SESSION_QUERY_KEY, getSession } from '../../api/session';
import { clearOwnerKey } from '../../lib/ownerKey';
import { Alert } from '../../components/Alert';
import { Button } from '../../components/Button';

/** The session query every part of the app shares. */
export function useSession() {
  return useQuery({
    queryKey: SESSION_QUERY_KEY,
    queryFn: getSession,
    // A rejected owner key or a server without owner access won't fix itself
    // on retry; a network blip might.
    retry: (failureCount, error) =>
      !(error instanceof ApiError && (error.status === 401 || error.status === 503)) && failureCount < 2,
    staleTime: 5 * 60_000,
  });
}

/**
 * Renders the app only once the visitor's session exists.
 *
 * The first request of a visit creates the demo sandbox and sets its cookie.
 * Letting the page's parallel queries be that first request would create one
 * sandbox per query, each with its own copy of the demo data — so this waits
 * for GET /api/session, and everything below it runs inside that one session.
 */
export function SessionGate({ children }: { children: ReactNode }) {
  const session = useSession();
  const queryClient = useQueryClient();

  if (session.isPending) {
    return (
      <div className="pp-session-gate" role="status" aria-live="polite">
        <span className="pp-skeleton pp-session-gate__bar" aria-hidden="true" />
        <p>Setting up your PawPal sandbox…</p>
      </div>
    );
  }

  if (session.isError) {
    const status = session.error instanceof ApiError ? session.error.status : 0;
    const ownerKeyProblem = status === 401 || status === 503;
    return (
      <div className="pp-session-gate">
        <Alert tone={ownerKeyProblem ? 'warning' : 'error'}>
          {status === 401 && 'That owner key was not accepted.'}
          {status === 503 && 'Owner access is not available on this server.'}
          {!ownerKeyProblem && 'PawPal could not start a session. Check your connection and try again.'}
        </Alert>
        <div className="pp-session-gate__actions">
          {ownerKeyProblem ? (
            <Button
              variant="primary"
              onClick={() => {
                clearOwnerKey();
                queryClient.resetQueries();
              }}
            >
              Forget the key and use the demo
            </Button>
          ) : (
            <Button variant="primary" onClick={() => session.refetch()}>
              Try again
            </Button>
          )}
        </div>
      </div>
    );
  }

  return <>{children}</>;
}
