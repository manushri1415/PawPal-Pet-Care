import { useState } from 'react';
import { Button } from '../../components/Button';
import { Dialog } from '../../components/Dialog';
import { ClockIcon } from '../../components/icons';
import { RoutineForm } from './RoutineForm';

/**
 * "Edit routine" in the top bar: opens the routine settings in a dialog. The
 * settings themselves are summarised in the greeting band on the Today page.
 */
export function EditRoutine() {
  const [open, setOpen] = useState(false);

  return (
    <>
      <Button
        variant="secondary"
        size="sm"
        className="pp-edit-routine"
        aria-haspopup="dialog"
        aria-expanded={open}
        onClick={() => setOpen(true)}
      >
        <ClockIcon />
        Edit routine
      </Button>

      <Dialog
        open={open}
        onClose={() => setOpen(false)}
        title="Your routine"
        description="Flexible tasks are planned inside these hours."
      >
        <RoutineForm onDone={() => setOpen(false)} onCancel={() => setOpen(false)} />
      </Dialog>
    </>
  );
}
