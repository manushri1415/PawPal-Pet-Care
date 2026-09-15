import './Dialog.css';
import { useEffect, useId, useRef } from 'react';
import type { ReactNode } from 'react';
import { Button } from './Button';
import { CloseIcon } from './icons';

/**
 * Modal dialog on the native <dialog> element (top layer, focus trap, Escape
 * to close). `open` is controlled by the parent; the content is mounted only
 * while open, so forms inside start fresh every time. Clicking the backdrop
 * closes it too.
 */
export function Dialog({
  open,
  onClose,
  title,
  description,
  children,
  className,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  description?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  const descriptionId = useId();

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    else if (!open && dialog.open) dialog.close();
  }, [open]);

  return (
    <dialog
      ref={ref}
      className={['pp-dialog', className].filter(Boolean).join(' ')}
      aria-labelledby={titleId}
      aria-describedby={description ? descriptionId : undefined}
      onCancel={(event) => {
        event.preventDefault();
        onClose();
      }}
      onClick={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      {open && (
        <div className="pp-dialog__panel">
          <header className="pp-dialog__head">
            <div className="pp-dialog__heading">
              <h2 id={titleId} className="pp-dialog__title">
                {title}
              </h2>
              {description && (
                <p id={descriptionId} className="pp-dialog__description">
                  {description}
                </p>
              )}
            </div>
            <Button variant="ghost" size="sm" iconOnly aria-label="Close" onClick={onClose}>
              <CloseIcon />
            </Button>
          </header>
          <div className="pp-dialog__body">{children}</div>
        </div>
      )}
    </dialog>
  );
}
