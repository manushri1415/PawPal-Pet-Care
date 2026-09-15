import './TaskList.css';
import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { TaskRead } from '../../api/types';
import { completeTask, deleteTask, listPets, listTasks, uncompleteTask } from '../../api/scheduler';
import { ApiError } from '../../api/client';
import { dayOffsetFromToday } from '../../lib/datetime';
import { Button } from '../../components/Button';
import { Alert } from '../../components/Alert';
import { EmptyState } from '../../components/EmptyState';
import { PlusIcon } from '../../components/icons';
import { PetArt } from '../../components/PetArt';
import { SectionHeading } from '../../components/SectionHeading';
import { useSlidingIndicator } from '../../components/useSlidingIndicator';
import { TaskForm } from './TaskForm';
import { TaskRow } from './TaskRow';

type StatusFilter = 'open' | 'completed' | 'all';
type SortOption = 'priority' | 'time' | 'duration';
type GroupKey = 'earlier' | 'today' | 'upcoming';

const STATUS_OPTIONS: { value: StatusFilter; label: string }[] = [
  { value: 'open', label: 'To do' },
  { value: 'completed', label: 'Done' },
  { value: 'all', label: 'All' },
];

const GROUP_ORDER: GroupKey[] = ['earlier', 'today', 'upcoming'];

function getErrorMessage(error: unknown): string {
  if (error instanceof ApiError && typeof error.detail === 'string') return error.detail;
  if (error instanceof Error) return error.message;
  return 'Something went wrong. Please try again.';
}

/** Buckets tasks by due day for display, preserving the API's order within each bucket. */
function groupByDay(tasks: TaskRead[]): Map<GroupKey, TaskRead[]> {
  const groups = new Map<GroupKey, TaskRead[]>();
  const now = new Date();
  for (const task of tasks) {
    const offset = dayOffsetFromToday(task.due_date, now) ?? 0;
    const key: GroupKey = offset < 0 ? 'earlier' : offset === 0 ? 'today' : 'upcoming';
    groups.set(key, [...(groups.get(key) ?? []), task]);
  }
  return groups;
}

export function TaskList() {
  const queryClient = useQueryClient();
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('open');
  const [petFilter, setPetFilter] = useState('');
  const [sort, setSort] = useState<SortOption | undefined>(undefined);
  const [showAddForm, setShowAddForm] = useState(false);
  const [editingTaskId, setEditingTaskId] = useState<string | null>(null);
  // The raised highlight of the To do / Done / All control slides to the pressed option.
  const segmentedRef = useSlidingIndicator<HTMLDivElement>(statusFilter, '[aria-pressed="true"]');

  const petsQuery = useQuery({ queryKey: ['pets'], queryFn: listPets });
  const tasksQuery = useQuery({
    queryKey: ['tasks', { petId: petFilter || undefined, status: statusFilter, sort }],
    queryFn: () => listTasks({ petId: petFilter || undefined, status: statusFilter, sort }),
  });

  const toggleCompleteMutation = useMutation({
    mutationFn: async (task: TaskRead) => {
      if (task.completed) {
        await uncompleteTask(task.task_id);
      } else {
        await completeTask(task.task_id);
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['tasks'] });
      queryClient.invalidateQueries({ queryKey: ['schedule'] });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (taskId: string) => deleteTask(taskId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['tasks'] });
      queryClient.invalidateQueries({ queryKey: ['schedule'] });
    },
  });

  const pets = petsQuery.data ?? [];
  const petById = new Map(pets.map((pet) => [pet.pet_id, pet]));
  const tasks = tasksQuery.data ?? [];
  const groups = groupByDay(tasks);
  const showGroupTitles = groups.size > 1 || !groups.has('today');
  const isUnfiltered = statusFilter === 'open' && !petFilter;

  const groupTitles: Record<GroupKey, string> = {
    earlier: statusFilter === 'open' ? 'Overdue' : 'Earlier',
    today: 'Today',
    upcoming: 'Coming up',
  };

  return (
    <section className="pp-tasks" aria-labelledby="pp-tasks-heading">
      <SectionHeading
        id="pp-tasks-heading"
        title="Today’s tasks"
        description="Check things off as you go. Repeating tasks come back on their own."
        actions={
          <Button variant="primary" size="sm" onClick={() => setShowAddForm(true)} disabled={showAddForm}>
            <PlusIcon />
            Add task
          </Button>
        }
      />

      <div className="pp-tasks__panel-wrap">
      {/* Peeks out from behind the panel's right edge on wide screens. */}
      <PetArt slot="tasks-peek" className="pp-tasks__peek" />

      <div className="pp-tasks__panel">
        <div className="pp-tasks__toolbar">
          <div ref={segmentedRef} className="pp-segmented" role="group" aria-label="Show tasks">
            {STATUS_OPTIONS.map((option) => (
              <button
                key={option.value}
                type="button"
                className="pp-segmented__option"
                aria-pressed={statusFilter === option.value}
                onClick={() => setStatusFilter(option.value)}
              >
                {option.label}
              </button>
            ))}
          </div>

          <div className="pp-tasks__selects">
            {pets.length > 0 && (
              <label className="pp-inline-select">
                <span>Pet</span>
                <select value={petFilter} onChange={(e) => setPetFilter(e.target.value)}>
                  <option value="">All pets</option>
                  {pets.map((pet) => (
                    <option key={pet.pet_id} value={pet.pet_id}>
                      {pet.name}
                    </option>
                  ))}
                </select>
              </label>
            )}

            <label className="pp-inline-select">
              <span>Sort</span>
              <select
                value={sort ?? ''}
                onChange={(e) => setSort(e.target.value === '' ? undefined : (e.target.value as SortOption))}
              >
                <option value="">Default</option>
                <option value="priority">Priority</option>
                <option value="time">Time</option>
                <option value="duration">Duration</option>
              </select>
            </label>
          </div>
        </div>

        {showAddForm && (
          <div className="pp-tasks__form">
            <TaskForm onDone={() => setShowAddForm(false)} onCancel={() => setShowAddForm(false)} />
          </div>
        )}

        {tasksQuery.isLoading && (
          <ul className="pp-task-rows" aria-label="Loading tasks">
            {[0, 1, 2].map((key) => (
              <li key={key} className="pp-skeleton pp-task-rows__skeleton" />
            ))}
          </ul>
        )}

        {tasksQuery.isError && <Alert tone="error">{getErrorMessage(tasksQuery.error)}</Alert>}
        {deleteMutation.isError && <Alert tone="error">{getErrorMessage(deleteMutation.error)}</Alert>}
        {toggleCompleteMutation.isError && (
          <Alert tone="error">{getErrorMessage(toggleCompleteMutation.error)}</Alert>
        )}

        {!tasksQuery.isLoading && !tasksQuery.isError && tasks.length === 0 &&
          (isUnfiltered ? (
            <EmptyState
              framed={false}
              compact
              art={['empty-tasks', 'empty-state']}
              title="All caught up"
              subtitle="No open tasks. Add one to start building a care routine."
            />
          ) : (
            <p className="pp-tasks__status">No tasks match these filters.</p>
          ))}

        {GROUP_ORDER.filter((key) => groups.has(key)).map((key) => {
          const groupTasks = groups.get(key) ?? [];
          const titleId = `pp-tasks-group-${key}`;
          return (
            <div key={key} className={`pp-tasks__group pp-tasks__group--${key}`}>
              {showGroupTitles && (
                <h3 id={titleId} className="pp-tasks__group-title">
                  {groupTitles[key]}
                  <span className="pp-tasks__group-count">{groupTasks.length}</span>
                </h3>
              )}
              <ul className="pp-task-rows" aria-labelledby={showGroupTitles ? titleId : 'pp-tasks-heading'}>
                {groupTasks.map((task) =>
                  editingTaskId === task.task_id ? (
                    <li key={task.task_id} className="pp-task-rows__form">
                      <TaskForm
                        task={task}
                        onDone={() => setEditingTaskId(null)}
                        onCancel={() => setEditingTaskId(null)}
                      />
                    </li>
                  ) : (
                    <TaskRow
                      key={task.task_id}
                      task={task}
                      pet={task.pet_id ? petById.get(task.pet_id) : undefined}
                      isToggling={
                        toggleCompleteMutation.isPending &&
                        toggleCompleteMutation.variables?.task_id === task.task_id
                      }
                      isDeleting={deleteMutation.isPending && deleteMutation.variables === task.task_id}
                      onToggle={() => toggleCompleteMutation.mutate(task)}
                      onEdit={() => setEditingTaskId(task.task_id)}
                      onDelete={() => deleteMutation.mutate(task.task_id)}
                    />
                  ),
                )}
              </ul>
            </div>
          );
        })}
      </div>
      </div>
    </section>
  );
}
