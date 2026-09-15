import './TaskForm.css';
import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { Category, Frequency, Priority, TaskRead } from '../../api/types';
import { CATEGORY_OPTIONS, FREQUENCY_OPTIONS, PRIORITY_OPTIONS } from '../../api/types';
import { createTask, listPets, updateTask } from '../../api/scheduler';
import { ApiError } from '../../api/client';
import { isoToLocalInput, localInputToIso } from '../../lib/datetime';
import { Alert } from '../../components/Alert';
import { Button } from '../../components/Button';

function getErrorMessage(error: unknown): string {
  if (error instanceof ApiError && typeof error.detail === 'string') return error.detail;
  if (error instanceof Error) return error.message;
  return 'Something went wrong. Please try again.';
}

export function TaskForm({
  task,
  onDone,
  onCancel,
}: {
  task?: TaskRead;
  onDone: () => void;
  onCancel: () => void;
}) {
  const isEdit = task !== undefined;
  const queryClient = useQueryClient();

  const [name, setName] = useState(task?.name ?? '');
  const [category, setCategory] = useState(task?.category ?? CATEGORY_OPTIONS[0]);
  const [petId, setPetId] = useState(task?.pet_id ?? '');
  const [duration, setDuration] = useState(String(task?.duration ?? 15));
  const [priority, setPriority] = useState(task?.priority ?? 'medium');
  const [frequency, setFrequency] = useState(task?.frequency ?? 'once');
  const [notes, setNotes] = useState(task?.notes ?? '');
  const [scheduledTime, setScheduledTime] = useState(task?.scheduled_time ?? '');
  const [dueDate, setDueDate] = useState(isoToLocalInput(task?.due_date));
  const [endDate, setEndDate] = useState(isoToLocalInput(task?.end_date));

  const { data: pets } = useQuery({ queryKey: ['pets'], queryFn: listPets });

  const mutation = useMutation({
    mutationFn: () => {
      const duePayload = localInputToIso(dueDate);
      const endPayload = localInputToIso(endDate);
      const resolvedPetId = petId ? petId : null;

      if (task) {
        return updateTask(task.task_id, {
          name,
          category,
          pet_id: resolvedPetId,
          duration: Number(duration),
          priority,
          frequency,
          notes,
          scheduled_time: scheduledTime,
          due_date: duePayload,
          end_date: endDate ? endPayload : null,
        });
      }

      return createTask({
        name,
        category,
        pet_id: resolvedPetId,
        duration: Number(duration),
        priority,
        frequency,
        notes,
        scheduled_time: scheduledTime,
        due_date: duePayload,
        end_date: endPayload,
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['tasks'] });
      queryClient.invalidateQueries({ queryKey: ['schedule'] });
      onDone();
    },
  });

  return (
    <form
      className="pp-task-form"
      onSubmit={(e) => {
        e.preventDefault();
        mutation.mutate();
      }}
    >
      <h3 className="pp-task-form-heading">{isEdit ? 'Edit task' : 'New task'}</h3>

      {mutation.isError && (
        <div className="pp-task-form-error">
          <Alert tone="error">{getErrorMessage(mutation.error)}</Alert>
        </div>
      )}

      <div className="pp-task-form-grid">
        <label>
          Name
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
          />
        </label>

        <label>
          Category
          <select value={category} onChange={(e) => setCategory(e.target.value as Category)}>
            {CATEGORY_OPTIONS.map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
          </select>
        </label>

        <label>
          Pet
          <select value={petId} onChange={(e) => setPetId(e.target.value)}>
            <option value="">No pet</option>
            {(pets ?? []).map((pet) => (
              <option key={pet.pet_id} value={pet.pet_id}>
                {pet.name}
              </option>
            ))}
          </select>
        </label>

        <label>
          Duration (minutes)
          <input
            type="number"
            min={0}
            value={duration}
            onChange={(e) => setDuration(e.target.value)}
            required
          />
        </label>

        <label>
          Priority
          <select value={priority} onChange={(e) => setPriority(e.target.value as Priority)}>
            {PRIORITY_OPTIONS.map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
          </select>
        </label>

        <label>
          Frequency
          <select value={frequency} onChange={(e) => setFrequency(e.target.value as Frequency)}>
            {FREQUENCY_OPTIONS.map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
          </select>
        </label>

        <label>
          Scheduled time
          <input
            type="text"
            placeholder="e.g. 14:30"
            value={scheduledTime}
            onChange={(e) => setScheduledTime(e.target.value)}
          />
        </label>

        <label>
          Due date
          <input
            type="datetime-local"
            value={dueDate}
            onChange={(e) => setDueDate(e.target.value)}
          />
        </label>

        <label>
          End date
          <input
            type="datetime-local"
            value={endDate}
            onChange={(e) => setEndDate(e.target.value)}
          />
        </label>

        <label className="pp-task-form-field--wide">
          Notes
          <textarea rows={3} value={notes} onChange={(e) => setNotes(e.target.value)} />
        </label>
      </div>

      <div className="pp-task-form-actions">
        <Button type="button" variant="secondary" onClick={onCancel}>
          Cancel
        </Button>
        <Button type="submit" variant="primary" disabled={mutation.isPending}>
          {mutation.isPending ? 'Saving…' : isEdit ? 'Save changes' : 'Add task'}
        </Button>
      </div>
    </form>
  );
}
