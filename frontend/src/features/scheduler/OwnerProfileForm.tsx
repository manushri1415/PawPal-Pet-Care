import './OwnerProfileForm.css';
import { useEffect, useState } from 'react';
import type { FormEvent } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Button } from '../../components/Button';
import { Alert } from '../../components/Alert';
import { getOwner, updateOwner } from '../../api/scheduler';
import type { OwnerRead, OwnerUpdate } from '../../api/types';

interface OwnerFormState {
  name: string;
  email: string;
  phone_number: string;
  available_hours_per_day: string;
  work_start: string;
  work_end: string;
  break_between_tasks_minutes: string;
}

const EMPTY_FORM: OwnerFormState = {
  name: '',
  email: '',
  phone_number: '',
  available_hours_per_day: '',
  work_start: '',
  work_end: '',
  break_between_tasks_minutes: '',
};

function pad2(n: number): string {
  return String(n).padStart(2, '0');
}

function clockLabel(hour: number, minute: number): string {
  const d = new Date();
  d.setHours(hour, minute, 0, 0);
  return d.toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' });
}

function routineFacts(owner: OwnerRead) {
  const hours = owner.available_hours_per_day;
  return [
    {
      label: 'Available',
      value: `${clockLabel(owner.work_start_hour, owner.work_start_minute)} – ${clockLabel(owner.work_end_hour, owner.work_end_minute)}`,
    },
    { label: 'Time for care', value: `${hours} ${hours === 1 ? 'hr' : 'hrs'} a day` },
    { label: 'Breaks', value: `${owner.break_between_tasks_minutes} min between tasks` },
    { label: 'Contact', value: [owner.name, owner.email].filter(Boolean).join(' · ') || '—' },
  ];
}

/**
 * Profile + routine settings — secondary content. Shows a one-line summary
 * and expands into the edit form on demand.
 */
export function OwnerProfileForm() {
  const queryClient = useQueryClient();
  const ownerQuery = useQuery({ queryKey: ['owner'], queryFn: getOwner });
  const [form, setForm] = useState<OwnerFormState>(EMPTY_FORM);
  const [showSuccess, setShowSuccess] = useState(false);
  const [isEditing, setIsEditing] = useState(false);

  useEffect(() => {
    const owner = ownerQuery.data;
    if (!owner) return;
    setForm({
      name: owner.name,
      email: owner.email,
      phone_number: owner.phone_number,
      available_hours_per_day: String(owner.available_hours_per_day),
      work_start: `${pad2(owner.work_start_hour)}:${pad2(owner.work_start_minute)}`,
      work_end: `${pad2(owner.work_end_hour)}:${pad2(owner.work_end_minute)}`,
      break_between_tasks_minutes: String(owner.break_between_tasks_minutes),
    });
  }, [ownerQuery.data]);

  const mutation = useMutation({
    mutationFn: updateOwner,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['owner'] });
      queryClient.invalidateQueries({ queryKey: ['schedule'] });
      setShowSuccess(true);
      setIsEditing(false);
    },
  });

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setShowSuccess(false);

    const [startHourStr, startMinuteStr] = form.work_start.split(':');
    const [endHourStr, endMinuteStr] = form.work_end.split(':');

    const patch: OwnerUpdate = {
      name: form.name,
      email: form.email,
      phone_number: form.phone_number,
      available_hours_per_day: Number(form.available_hours_per_day),
      work_start_hour: Number(startHourStr ?? 0),
      work_start_minute: Number(startMinuteStr ?? 0),
      work_end_hour: Number(endHourStr ?? 0),
      work_end_minute: Number(endMinuteStr ?? 0),
      break_between_tasks_minutes: Number(form.break_between_tasks_minutes),
    };

    mutation.mutate(patch);
  }

  return (
    <section className="pp-routine" aria-labelledby="pp-routine-heading">
      <div className="pp-routine__summary">
        <div className="pp-routine__intro">
          <h2 id="pp-routine-heading" className="pp-routine__title">
            Your routine
          </h2>
          <p className="pp-routine__description">Flexible tasks are planned inside these hours.</p>
        </div>

        {ownerQuery.data && !isEditing && (
          <dl className="pp-routine__facts">
            {routineFacts(ownerQuery.data).map((fact) => (
              <div key={fact.label}>
                <dt>{fact.label}</dt>
                <dd>{fact.value}</dd>
              </div>
            ))}
          </dl>
        )}

        {ownerQuery.isLoading && <p className="pp-routine__loading">Loading your routine…</p>}

        {ownerQuery.data && (
          <Button
            variant="secondary"
            size="sm"
            className="pp-routine__toggle"
            aria-expanded={isEditing}
            aria-controls="pp-routine-form"
            onClick={() => {
              setShowSuccess(false);
              setIsEditing((current) => !current);
            }}
          >
            {isEditing ? 'Close' : 'Edit routine'}
          </Button>
        )}
      </div>

      {ownerQuery.isError && (
        <Alert tone="error">
          {ownerQuery.error instanceof Error ? ownerQuery.error.message : 'Failed to load owner profile.'}
        </Alert>
      )}

      {showSuccess && !mutation.isPending && <Alert tone="success">Routine saved.</Alert>}

      {ownerQuery.data && isEditing && (
        <form id="pp-routine-form" className="pp-owner-profile-form__form" onSubmit={handleSubmit}>
          <fieldset className="pp-owner-profile-form__group">
            <legend>Your day</legend>
            <div className="pp-owner-profile-form__grid">
              <div>
                <label htmlFor="pp-owner-work-start">Available from</label>
                <input
                  id="pp-owner-work-start"
                  type="time"
                  value={form.work_start}
                  onChange={(e) => setForm((f) => ({ ...f, work_start: e.target.value }))}
                  required
                />
              </div>

              <div>
                <label htmlFor="pp-owner-work-end">Available until</label>
                <input
                  id="pp-owner-work-end"
                  type="time"
                  value={form.work_end}
                  onChange={(e) => setForm((f) => ({ ...f, work_end: e.target.value }))}
                  required
                />
              </div>

              <div>
                <label htmlFor="pp-owner-hours">Hours for care per day</label>
                <input
                  id="pp-owner-hours"
                  type="number"
                  step={0.5}
                  min={0}
                  value={form.available_hours_per_day}
                  onChange={(e) => setForm((f) => ({ ...f, available_hours_per_day: e.target.value }))}
                  required
                />
              </div>

              <div>
                <label htmlFor="pp-owner-break">Break between tasks (min)</label>
                <input
                  id="pp-owner-break"
                  type="number"
                  min={0}
                  value={form.break_between_tasks_minutes}
                  onChange={(e) => setForm((f) => ({ ...f, break_between_tasks_minutes: e.target.value }))}
                  required
                />
              </div>
            </div>
          </fieldset>

          <fieldset className="pp-owner-profile-form__group">
            <legend>About you</legend>
            <div className="pp-owner-profile-form__grid">
              <div>
                <label htmlFor="pp-owner-name">Name</label>
                <input
                  id="pp-owner-name"
                  type="text"
                  value={form.name}
                  onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
                  required
                />
              </div>

              <div>
                <label htmlFor="pp-owner-email">Email</label>
                <input
                  id="pp-owner-email"
                  type="text"
                  value={form.email}
                  onChange={(e) => setForm((f) => ({ ...f, email: e.target.value }))}
                  required
                />
              </div>

              <div>
                <label htmlFor="pp-owner-phone">Phone number</label>
                <input
                  id="pp-owner-phone"
                  type="text"
                  value={form.phone_number}
                  onChange={(e) => setForm((f) => ({ ...f, phone_number: e.target.value }))}
                />
              </div>
            </div>
          </fieldset>

          {mutation.isError && (
            <Alert tone="error">
              {mutation.error instanceof Error ? mutation.error.message : 'Failed to save profile.'}
            </Alert>
          )}

          <div className="pp-owner-profile-form__actions">
            <Button variant="secondary" type="button" onClick={() => setIsEditing(false)}>
              Cancel
            </Button>
            <Button variant="primary" type="submit" disabled={mutation.isPending}>
              {mutation.isPending ? 'Saving…' : 'Save routine'}
            </Button>
          </div>
        </form>
      )}
    </section>
  );
}
