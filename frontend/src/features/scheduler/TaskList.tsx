import './TaskList.css';
import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { TaskRead } from '../../api/types';
import { completeTask, deleteTask, listPets, listTasks, uncompleteTask } from '../../api/scheduler';
import { ApiError } from '../../api/client';
import { formatDate } from '../../lib/datetime';
import { Card } from '../../components/Card';
import { Eyebrow } from '../../components/Eyebrow';
import { Tag } from '../../components/Tag';
import { DotBadge, PRIORITY_COLORS } from '../../components/DotBadge';
import { Button } from '../../components/Button';
import { Alert } from '../../components/Alert';
import { EmptyState } from '../../components/EmptyState';
import { TaskForm } from './TaskForm';

type StatusFilter = 'open' | 'completed' | 'all';
type SortOption = 'priority' | 'time' | 'duration';

function getErrorMessage(error: unknown): string {
  if (error instanceof ApiError && typeof error.detail === 'string') return error.detail;
  if (error instanceof Error) return error.message;
  return 'Something went wrong. Please try again.';
}

export function TaskList() {
  const queryClient = useQueryClient();
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('open');
  const [petFilter, setPetFilter] = useState('');
  const [sort, setSort] = useState<SortOption | undefined>(undefined);
  const [showAddForm, setShowAddForm] = useState(false);
  const [editingTaskId, setEditingTaskId] = useState<string | null>(null);

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
  const petNameById = new Map(pets.map((pet) => [pet.pet_id, pet.name]));
  const tasks = tasksQuery.data ?? [];

  return (
    <div className="pp-task-list">
      <Eyebrow label="Tasks" tone="lavender" large />
      <Card tone="plain">
        <div className="pp-task-list-filters">
          <label className="pp-task-list-filter">
            Status
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value as StatusFilter)}
            >
              <option value="open">Open</option>
              <option value="completed">Completed</option>
              <option value="all">All</option>
            </select>
          </label>

          <label className="pp-task-list-filter">
            Pet
            <select value={petFilter} onChange={(e) => setPetFilter(e.target.value)}>
              <option value="">All pets</option>
              {pets.map((pet) => (
                <option key={pet.pet_id} value={pet.pet_id}>
                  {pet.name}
                </option>
              ))}
            </select>
          </label>

          <label className="pp-task-list-filter">
            Sort by
            <select
              value={sort ?? ''}
              onChange={(e) =>
                setSort(e.target.value === '' ? undefined : (e.target.value as SortOption))
              }
            >
              <option value="">Default</option>
              <option value="priority">Priority</option>
              <option value="time">Time</option>
              <option value="duration">Duration</option>
            </select>
          </label>

          {!showAddForm && (
            <div className="pp-task-list-add">
              <Button variant="primary" onClick={() => setShowAddForm(true)}>
                Add task
              </Button>
            </div>
          )}
        </div>

        {showAddForm && (
          <TaskForm onDone={() => setShowAddForm(false)} onCancel={() => setShowAddForm(false)} />
        )}

        {tasksQuery.isLoading && <p className="pp-task-list-loading">Loading tasks…</p>}

        {tasksQuery.isError && <Alert tone="error">{getErrorMessage(tasksQuery.error)}</Alert>}
        {deleteMutation.isError && (
          <Alert tone="error">{getErrorMessage(deleteMutation.error)}</Alert>
        )}
        {toggleCompleteMutation.isError && (
          <Alert tone="error">{getErrorMessage(toggleCompleteMutation.error)}</Alert>
        )}

        {!tasksQuery.isLoading && !tasksQuery.isError && tasks.length === 0 && (
          <EmptyState
            title="No tasks yet"
            subtitle="Add a task to start building today's care routine."
          />
        )}

        {tasks.length > 0 && (
          <div className="pp-task-list-rows">
            {tasks.map((task) => {
              if (editingTaskId === task.task_id) {
                return (
                  <TaskForm
                    key={task.task_id}
                    task={task}
                    onDone={() => setEditingTaskId(null)}
                    onCancel={() => setEditingTaskId(null)}
                  />
                );
              }

              const petName = task.pet_id ? petNameById.get(task.pet_id) : undefined;

              return (
                <div
                  key={task.task_id}
                  className={
                    task.completed
                      ? 'pp-task-list-row pp-task-list-row--completed'
                      : 'pp-task-list-row'
                  }
                >
                  <DotBadge label={task.priority} color={PRIORITY_COLORS[task.priority]} />
                  <span className="pp-task-list-name">{task.name}</span>
                  <Tag tone="lavender">{task.category}</Tag>
                  {petName && <span className="pp-task-list-pet">{petName}</span>}
                  {task.due_date && (
                    <span className="pp-task-list-date">{formatDate(task.due_date)}</span>
                  )}
                  <div className="pp-task-list-actions">
                    <Button
                      variant="secondary"
                      disabled={
                        toggleCompleteMutation.isPending &&
                        toggleCompleteMutation.variables?.task_id === task.task_id
                      }
                      onClick={() => toggleCompleteMutation.mutate(task)}
                    >
                      {task.completed ? 'Uncomplete' : 'Complete'}
                    </Button>
                    <Button variant="secondary" onClick={() => setEditingTaskId(task.task_id)}>
                      Edit
                    </Button>
                    <Button
                      variant="secondary"
                      className="pp-task-list-delete"
                      disabled={
                        deleteMutation.isPending && deleteMutation.variables === task.task_id
                      }
                      onClick={() => deleteMutation.mutate(task.task_id)}
                    >
                      Delete
                    </Button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </Card>
    </div>
  );
}
