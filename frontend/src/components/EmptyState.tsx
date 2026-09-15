import './EmptyState.css';
import type { ReactNode } from 'react';
import type { ArtSlot } from '../art/registry';
import { PetArt } from './PetArt';

/**
 * EmptyState — illustration area, heading, supporting message, optional CTA.
 * The illustration comes from the art registry (`art` defaults to the shared
 * 'empty-state' slot, which is deliberately left empty so that the same
 * picture never shows up in two empty states on one page; pass a section
 * slot first to give a particular empty state its own) and is skipped
 * entirely while nothing is registered, so the block stays tidy.
 *
 * `framed` (default) draws the stationery-style dashed panel; turn it off
 * when the empty state already sits inside a card. `compact` lays the
 * illustration and text side by side where there's room.
 */
export function EmptyState({
  title,
  subtitle,
  action,
  art = 'empty-state',
  framed = true,
  compact = false,
  className,
}: {
  title: string;
  subtitle?: ReactNode;
  action?: ReactNode;
  art?: ArtSlot | ArtSlot[] | null;
  framed?: boolean;
  compact?: boolean;
  className?: string;
}) {
  const classes = [
    'pp-empty',
    framed && 'pp-empty--framed',
    compact && 'pp-empty--compact',
    className,
  ]
    .filter(Boolean)
    .join(' ');

  return (
    <div className={classes}>
      {art && <PetArt slot={art} className="pp-empty__art" />}
      <div className="pp-empty__body">
        <p className="pp-empty__title">{title}</p>
        {subtitle && <p className="pp-empty__text">{subtitle}</p>}
        {action && <div className="pp-empty__action">{action}</div>}
      </div>
    </div>
  );
}
