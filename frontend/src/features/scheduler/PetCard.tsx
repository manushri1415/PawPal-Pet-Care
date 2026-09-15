import type { PetRead } from '../../api/types';
import { Alert } from '../../components/Alert';
import { Button } from '../../components/Button';
import { PencilIcon, PlusIcon, TrashIcon } from '../../components/icons';
import { PetArt } from '../../components/PetArt';
import { PetAvatar } from '../../components/PetAvatar';
import { capitalize, petAgeLabel, petTone } from '../../lib/display';

export interface PetDeleteIssue {
  tone: 'warning' | 'error';
  message: string;
}

/** Rich profile card for one pet. Purely presentational — PetList owns the mutations. */
export function PetCard({
  pet,
  openTaskCount,
  isDeleting,
  issue,
  onEdit,
  onDelete,
  onForceDelete,
}: {
  pet: PetRead;
  openTaskCount: number | undefined;
  isDeleting: boolean;
  issue: PetDeleteIssue | null;
  onEdit: () => void;
  onDelete: () => void;
  onForceDelete: () => void;
}) {
  const subtitle = [capitalize(pet.pet_type), pet.gender !== 'unknown' ? capitalize(pet.gender) : null]
    .filter(Boolean)
    .join(' · ');

  return (
    <article className={`pp-pet-card pp-tone--${petTone(pet)}`} aria-label={pet.name}>
      <div className="pp-pet-card__banner" />
      <div className="pp-pet-card__actions">
        <Button variant="ghost" size="sm" iconOnly onClick={onEdit} aria-label={`Edit ${pet.name}`} title="Edit">
          <PencilIcon />
        </Button>
        <Button
          variant="danger"
          size="sm"
          iconOnly
          onClick={onDelete}
          disabled={isDeleting}
          aria-label={`Remove ${pet.name}`}
          title="Remove"
        >
          <TrashIcon />
        </Button>
      </div>

      <PetAvatar pet={pet} size="lg" className="pp-pet-card__avatar" />
      <h3 className="pp-pet-card__name">{pet.name}</h3>
      <p className="pp-pet-card__subtitle">{subtitle}</p>

      <dl className="pp-pet-card__facts">
        <div>
          <dt>Age</dt>
          <dd>{petAgeLabel(pet)}</dd>
        </div>
        <div>
          <dt>Coat</dt>
          <dd>{pet.color ? capitalize(pet.color) : '—'}</dd>
        </div>
      </dl>

      <p className="pp-pet-card__tasks">
        {openTaskCount === undefined
          ? ' '
          : openTaskCount === 0
            ? 'No open care tasks'
            : `${openTaskCount} open care ${openTaskCount === 1 ? 'task' : 'tasks'}`}
      </p>

      {issue && (
        <div className="pp-pet-card__issue">
          <Alert tone={issue.tone}>{issue.message}</Alert>
          {issue.tone === 'warning' && (
            <Button variant="secondary" size="sm" disabled={isDeleting} onClick={onForceDelete}>
              Delete anyway
            </Button>
          )}
        </div>
      )}
    </article>
  );
}

/** Same grid footprint as a PetCard; the optional `add-pet-motif` art sits above the plus. */
export function AddPetCard({ onClick }: { onClick: () => void }) {
  return (
    <button type="button" className="pp-add-pet-card" onClick={onClick}>
      <PetArt slot="add-pet-motif" className="pp-add-pet-card__motif" />
      <span className="pp-add-pet-card__icon">
        <PlusIcon />
      </span>
      <span className="pp-add-pet-card__title">Add a pet</span>
      <span className="pp-add-pet-card__text">Set up a profile for a new companion</span>
    </button>
  );
}
