import type { PetRead, Priority, TaskRead } from '../../api/types';
import { Button } from '../../components/Button';
import { CheckIcon, ClockIcon, PencilIcon, RepeatIcon, TrashIcon } from '../../components/icons';
import { PetAvatar } from '../../components/PetAvatar';
import { formatClockTime, formatRelativeDay } from '../../lib/datetime';
import {
  CATEGORY_LABELS,
  CATEGORY_TONES,
  FREQUENCY_LABELS,
  PRIORITY_LABELS,
  durationLabel,
} from '../../lib/display';
import type { Tone } from '../../lib/display';

const PRIORITY_TONES: Record<Priority, Tone> = {
  high: 'terracotta',
  medium: 'ochre',
  low: 'sage',
};

/** One compact task row. Presentational — TaskList owns the mutations. */
export function TaskRow({
  task,
  pet,
  isToggling,
  isDeleting,
  onToggle,
  onEdit,
  onDelete,
}: {
  task: TaskRead;
  pet: PetRead | undefined;
  isToggling: boolean;
  isDeleting: boolean;
  onToggle: () => void;
  onEdit: () => void;
  onDelete: () => void;
}) {
  const when = [formatRelativeDay(task.due_date), task.scheduled_time ? formatClockTime(task.scheduled_time) : null]
    .filter(Boolean)
    .join(' · ');

  return (
    <li className={['pp-task-row', task.completed && 'pp-task-row--done'].filter(Boolean).join(' ')}>
      <button
        type="button"
        className="pp-task-row__check"
        aria-pressed={task.completed}
        aria-label={task.completed ? `Mark “${task.name}” as not done` : `Mark “${task.name}” as done`}
        disabled={isToggling}
        onClick={onToggle}
      >
        <CheckIcon />
      </button>

      <div className="pp-task-row__main">
        <span className="pp-task-row__name">{task.name}</span>
        {(task.frequency !== 'once' || task.notes) && (
          <span className="pp-task-row__sub">
            {task.frequency !== 'once' && (
              <span className="pp-task-row__repeat">
                <RepeatIcon />
                {FREQUENCY_LABELS[task.frequency]}
              </span>
            )}
            {task.notes && <span className="pp-task-row__notes">{task.notes}</span>}
          </span>
        )}
      </div>

      <div className="pp-task-row__meta">
        <span className={['pp-task-row__pet', !pet && 'pp-task-row__pet--none'].filter(Boolean).join(' ')}>
          <PetAvatar pet={pet} size="xs" />
          {pet ? pet.name : 'No pet'}
        </span>

        <span className={`pp-task-row__category pp-tone--${CATEGORY_TONES[task.category]}`}>
          <span className="pp-task-row__category-dot" aria-hidden="true" />
          {CATEGORY_LABELS[task.category]}
        </span>

        <span className="pp-task-row__when">
          <ClockIcon />
          <span>
            {when}
            <span className="pp-task-row__duration"> · {durationLabel(task.duration)}</span>
          </span>
        </span>

        <span
          className={[
            'pp-pill',
            'pp-task-row__priority',
            `pp-tone--${PRIORITY_TONES[task.priority]}`,
            task.priority !== 'high' && 'pp-task-row__priority--quiet',
          ]
            .filter(Boolean)
            .join(' ')}
        >
          <span className="pp-pill__dot" />
          {PRIORITY_LABELS[task.priority]}
          <span className="pp-visually-hidden"> priority</span>
        </span>
      </div>

      <div className="pp-task-row__actions">
        <Button variant="ghost" size="sm" iconOnly onClick={onEdit} aria-label={`Edit “${task.name}”`} title="Edit">
          <PencilIcon />
        </Button>
        <Button
          variant="danger"
          size="sm"
          iconOnly
          disabled={isDeleting}
          onClick={onDelete}
          aria-label={`Delete “${task.name}”`}
          title="Delete"
        >
          <TrashIcon />
        </Button>
      </div>
    </li>
  );
}
