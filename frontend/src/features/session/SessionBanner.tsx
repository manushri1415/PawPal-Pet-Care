import './Session.css';
import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { resetDemo } from '../../api/session';
import { Alert } from '../../components/Alert';
import { Button } from '../../components/Button';
import { Dialog } from '../../components/Dialog';
import { DotBadge } from '../../components/DotBadge';
import { useSession } from './SessionGate';

/** "about 47 hours" / "about 2 days" / "less than an hour". */
function timeLeft(expiresAt: string, now = Date.now()): string {
  const hours = (new Date(expiresAt).getTime() - now) / 3_600_000;
  if (hours < 1) return 'less than an hour';
  if (hours < 36) {
    const h = Math.round(hours);
    return `about ${h} hour${h === 1 ? '' : 's'}`;
  }
  return `about ${Math.round(hours / 24)} days`;
}

/**
 * One quiet line above the page saying whose data this is: a private demo
 * sandbox (with when it goes away and a way to start over), or the owner space.
 */
export function SessionBanner() {
  const session = useSession();
  const queryClient = useQueryClient();
  const [confirmOpen, setConfirmOpen] = useState(false);

  const reset = useMutation({
    mutationFn: resetDemo,
    onSuccess: () => {
      setConfirmOpen(false);
      // Every cached pet, task and record belonged to the old sandbox.
      queryClient.resetQueries();
    },
  });

  if (!session.data) return null;

  if (session.data.kind === 'owner') {
    return (
      <div className="pp-session-banner" role="note">
        <DotBadge label="Owner space" color="var(--pp-sage)" />
        <span className="pp-session-banner__text">Your own data, kept until you delete it.</span>
      </div>
    );
  }

  return (
    <div className="pp-session-banner" role="note">
      <DotBadge label="Demo sandbox" color="var(--pp-plum)" />
      <span className="pp-session-banner__text">
        Private to this browser. Explore freely — it resets in{' '}
        {session.data.expires_at ? timeLeft(session.data.expires_at) : 'a couple of days'}.
      </span>
      <Button variant="ghost" size="sm" className="pp-session-banner__reset" onClick={() => setConfirmOpen(true)}>
        Reset demo
      </Button>

      <Dialog
        open={confirmOpen}
        onClose={() => setConfirmOpen(false)}
        title="Reset the demo?"
        description="Everything you added or changed in this sandbox is deleted, and the sample pets, routine and health records come back."
      >
        {reset.isError && <Alert tone="error">The demo could not be reset. Please try again.</Alert>}
        <div className="pp-session-banner__confirm">
          <Button variant="secondary" onClick={() => setConfirmOpen(false)} disabled={reset.isPending}>
            Keep my changes
          </Button>
          <Button variant="danger" onClick={() => reset.mutate()} disabled={reset.isPending}>
            {reset.isPending ? 'Resetting…' : 'Reset demo'}
          </Button>
        </div>
      </Dialog>
    </div>
  );
}
