import './ScheduleView.css';
import { useEffect, useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { Alert } from '../../components/Alert';
import { Button } from '../../components/Button';
import { EmptyState } from '../../components/EmptyState';
import { PetArt } from '../../components/PetArt';
import { PetAvatar } from '../../components/PetAvatar';
import { SectionHeading } from '../../components/SectionHeading';
import { generateSchedule, listPets } from '../../api/scheduler';
import { formatDate, formatTime } from '../../lib/datetime';
import { CATEGORY_LABELS, CATEGORY_TONES, durationLabel } from '../../lib/display';

function todayInputValue(): string {
  const d = new Date();
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

export function ScheduleView() {
  const [date, setDate] = useState('');
  // The date is passed as the mutation variable (rather than read from state
  // inside mutationFn) so the rendered plan always knows which day it is for.
  const mutation = useMutation({
    mutationFn: (forDate: string) => generateSchedule(forDate || undefined),
  });
  const petsQuery = useQuery({ queryKey: ['pets'], queryFn: listPets });

  useEffect(() => {
    mutation.mutate('');
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const shownDate = mutation.variables ?? '';
  const isToday = shownDate === '' || shownDate === todayInputValue();
  const petById = new Map((petsQuery.data ?? []).map((pet) => [pet.pet_id, pet]));

  const items = mutation.isSuccess
    ? [...mutation.data.schedule].sort((a, b) => new Date(a.start).getTime() - new Date(b.start).getTime())
    : [];
  const now = Date.now();
  const nextIndex = isToday ? items.findIndex((item) => new Date(item.end).getTime() > now) : -1;
  const totalMinutes = items.reduce((sum, item) => sum + item.task.duration, 0);

  let description = 'Your day, planned around your routine.';
  if (mutation.isSuccess && items.length > 0) {
    description = `${items.length} ${items.length === 1 ? 'activity' : 'activities'} · ${durationLabel(totalMinutes)} of care planned`;
  }

  return (
    <section className="pp-schedule" aria-labelledby="pp-schedule-heading">
      <div className="pp-schedule__head">
        <SectionHeading
          id="pp-schedule-heading"
          title={isToday ? 'Today’s schedule' : `Schedule for ${formatDate(shownDate)}`}
          description={description}
        />
        <PetArt slot="schedule-corner" className="pp-schedule__corner" />
      </div>

      <div className="pp-schedule__card">
        <form
          className="pp-schedule__controls"
          onSubmit={(event) => {
            event.preventDefault();
            mutation.mutate(date);
          }}
        >
          <label className="pp-schedule__date">
            <span>Plan for</span>
            <input
              type="date"
              value={date}
              onChange={(event) => setDate(event.target.value)}
              aria-label="Schedule date"
            />
          </label>
          <Button type="submit" variant="secondary" size="sm" disabled={mutation.isPending}>
            {mutation.isPending ? 'Planning…' : 'Update plan'}
          </Button>
        </form>

        {mutation.isPending && (
          <ul className="pp-timeline pp-timeline--loading" aria-label="Loading schedule">
            {[0, 1, 2].map((key) => (
              <li key={key} className="pp-skeleton pp-timeline__skeleton" />
            ))}
          </ul>
        )}

        {mutation.isError && <Alert tone="error">{mutation.error.message}</Alert>}

        {mutation.isSuccess && items.length === 0 && (
          <EmptyState
            framed={false}
            art={['empty-schedule', 'empty-state']}
            title="A quiet day"
            subtitle="Nothing is scheduled yet. Tasks you add are planned into your day automatically."
          />
        )}

        {items.length > 0 && (
          <ol className="pp-timeline">
            {items.map((item, index) => {
              const pet = item.task.pet_id ? petById.get(item.task.pet_id) : undefined;
              const isNext = index === nextIndex;
              const isPast = isToday && new Date(item.end).getTime() <= now;
              const rowClass = [
                'pp-timeline__item',
                `pp-tone--${CATEGORY_TONES[item.task.category]}`,
                isNext && 'pp-timeline__item--next',
                isPast && 'pp-timeline__item--past',
              ]
                .filter(Boolean)
                .join(' ');

              return (
                <li key={item.task.task_id} className={rowClass} aria-current={isNext ? 'step' : undefined}>
                  <div className="pp-timeline__time">
                    <span className="pp-timeline__start">{formatTime(item.start)}</span>
                    <span className="pp-timeline__end">{formatTime(item.end)}</span>
                  </div>
                  <span className="pp-timeline__dot" aria-hidden="true" />
                  <div className="pp-timeline__body">
                    <div className="pp-timeline__main">
                      <span className="pp-timeline__name">{item.task.name}</span>
                      <span className="pp-timeline__meta">
                        {CATEGORY_LABELS[item.task.category]} · {durationLabel(item.task.duration)}
                        {pet ? ` · ${pet.name}` : ''}
                      </span>
                    </div>
                    <div className="pp-timeline__badges">
                      {isNext && <span className="pp-pill pp-pill--solid pp-tone--peach">Up next</span>}
                      {item.task.priority === 'high' && (
                        <span className="pp-pill pp-tone--terracotta">
                          <span className="pp-pill__dot" />
                          High
                        </span>
                      )}
                      {pet && <PetAvatar pet={pet} size="sm" />}
                    </div>
                  </div>
                </li>
              );
            })}
          </ol>
        )}

        {mutation.isSuccess && mutation.data.conflicts.length > 0 && (
          <div className="pp-schedule__conflicts">
            <Alert tone="warning">
              <p className="pp-schedule__conflicts-heading">Some activities overlap</p>
              <ul>
                {mutation.data.conflicts.map((conflict) => (
                  <li key={conflict}>{conflict}</li>
                ))}
              </ul>
            </Alert>
          </div>
        )}
      </div>
    </section>
  );
}
