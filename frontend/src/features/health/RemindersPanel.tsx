import './RemindersPanel.css';
import { useEffect, useRef } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { listConflicts, listReminders, resolveConflict, scheduleCare } from '../../api/health';
import { ApiError } from '../../api/client';
import { formatDate, parseDateOnly } from '../../lib/datetime';
import { Alert } from '../../components/Alert';
import { Button } from '../../components/Button';
import { Card } from '../../components/Card';
import { EmptyState } from '../../components/EmptyState';
import { Eyebrow } from '../../components/Eyebrow';
import { Tag } from '../../components/Tag';
import { CARE_STATUS_COLORS, CARE_STATUS_LABELS, DotBadge } from '../../components/DotBadge';

function getErrorMessage(error: unknown): string {
  if (error instanceof ApiError && typeof error.detail === 'string') return error.detail;
  if (error instanceof Error) return error.message;
  return 'Something went wrong. Please try again.';
}

/** "Rabies vaccine (annual booster)" -> "Rabies vaccine" — drop a trailing
 * parenthetical so the card title stays a clean noun phrase. */
function reminderName(label: string): string {
  return label.replace(/\s+\([^)]+\)$/, '').trim();
}

/** "due_date" -> "Due Date", "vaccination" -> "Vaccination". */
function humanize(value: string): string {
  return value.replace(/_/g, ' ').replace(/\b\w/g, (char) => char.toUpperCase());
}

/** "Source A" -> "Source A — page 2" (falls back to "record excerpt" when the
 * evidence has no section identifier), mirroring the old page's
 * `_source_label` caption under each conflict. */
function sourceLabel(source: { section: string | null } | null, fallback: string): string {
  if (!source) return fallback;
  return `${fallback} — ${source.section || 'record excerpt'}`;
}

/** due_date vs. today -> "Due today" / "Due tomorrow" / "N days overdue" /
 * "Due in N days", mirroring the old Streamlit page's _relative_due_text. */
function relativeDueText(dueDate: string): string {
  const due = parseDateOnly(dueDate) ?? new Date(dueDate);
  if (Number.isNaN(due.getTime())) return '';
  const today = new Date();
  const days = Math.round((due.getTime() - today.getTime()) / 86_400_000);
  if (days === 0) return 'Due today';
  if (days < 0) return `${Math.abs(days)} days overdue`;
  if (days === 1) return 'Due tomorrow';
  return `Due in ${days} days`;
}

/** [30, 14, 1, 0] -> "30 days before, 14 days before, 1 day before, on the due date". */
function formatOffsets(offsetsDays: number[]): string {
  return [...offsetsDays]
    .sort((a, b) => b - a)
    .map((days) => {
      if (days === 0) return 'on the due date';
      if (days === 1) return '1 day before';
      return `${days} days before`;
    })
    .join(', ');
}

export function RemindersPanel({ petId }: { petId: string }) {
  const queryClient = useQueryClient();

  const remindersQuery = useQuery({
    queryKey: ['health', 'reminders', petId],
    queryFn: () => listReminders(petId),
  });

  const conflictsQuery = useQuery({
    queryKey: ['health', 'conflicts', petId, true],
    queryFn: () => listConflicts(petId, true),
  });

  const scheduleCareMutation = useMutation({
    mutationFn: () => scheduleCare(petId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['health', 'reminders'] });
      queryClient.invalidateQueries({ queryKey: ['health', 'conflicts'] });
    },
  });

  const resolveMutation = useMutation({
    mutationFn: (conflictId: string) => resolveConflict(conflictId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['health', 'conflicts'] });
    },
  });

  // Recompute reminders/conflicts once per pet. Guarded by petId (not just a
  // boolean) so React 19 StrictMode's dev double-invoke is a no-op, but
  // switching pets still triggers a fresh recalculation — the endpoint is
  // idempotent server-side either way.
  const scheduledForRef = useRef<string | null>(null);
  useEffect(() => {
    if (scheduledForRef.current === petId) return;
    scheduledForRef.current = petId;
    scheduleCareMutation.mutate();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [petId]);

  const reminders = remindersQuery.data ?? [];
  const conflicts = conflictsQuery.data ?? [];
  const sortedReminders = [...reminders].sort(
    (a, b) =>
      (parseDateOnly(a.due_date) ?? new Date(a.due_date)).getTime() -
      (parseDateOnly(b.due_date) ?? new Date(b.due_date)).getTime(),
  );

  const isLoading = remindersQuery.isLoading || conflictsQuery.isLoading;
  const showEmptyState =
    !isLoading &&
    !remindersQuery.isError &&
    !conflictsQuery.isError &&
    reminders.length === 0 &&
    conflicts.length === 0;

  return (
    <div className="pp-reminders-panel">
      <Eyebrow label="Reminders" tone="sage" large />

      <Card tone="plain">
        <div className="pp-reminders-panel__header">
          <Button
            variant="secondary"
            disabled={scheduleCareMutation.isPending}
            onClick={() => scheduleCareMutation.mutate()}
          >
            {scheduleCareMutation.isPending ? 'Recalculating…' : 'Recalculate'}
          </Button>
        </div>

        {scheduleCareMutation.isError && (
          <Alert tone="error">{getErrorMessage(scheduleCareMutation.error)}</Alert>
        )}

        {isLoading && <p className="pp-reminders-panel__status">Loading reminders…</p>}

        {remindersQuery.isError && (
          <Alert tone="error">{getErrorMessage(remindersQuery.error)}</Alert>
        )}
        {conflictsQuery.isError && (
          <Alert tone="error">{getErrorMessage(conflictsQuery.error)}</Alert>
        )}

        {conflicts.length > 0 && (
          <div className="pp-reminders-panel__conflicts">
            <Alert tone="error">
              {conflicts.length} unresolved contradiction(s); reminders are paused for affected
              records.
            </Alert>

            {resolveMutation.isError && (
              <Alert tone="error">{getErrorMessage(resolveMutation.error)}</Alert>
            )}

            <div className="pp-reminders-panel__conflict-list">
              {conflicts.map((conflict) => (
                <div key={conflict.conflict_id} className="pp-reminders-panel__conflict">
                  <div className="pp-reminders-panel__conflict-field">
                    Conflicting {humanize(conflict.record_type)} {humanize(conflict.field)}
                  </div>
                  <div className="pp-reminders-panel__conflict-values">
                    <span>{conflict.value_a}</span>
                    <span className="pp-reminders-panel__conflict-vs">vs</span>
                    <span>{conflict.value_b}</span>
                  </div>
                  {(conflict.source_a || conflict.source_b) && (
                    <div className="pp-reminders-panel__conflict-sources">
                      {sourceLabel(conflict.source_a, 'Source A')}; {sourceLabel(conflict.source_b, 'Source B')}
                    </div>
                  )}
                  <Button
                    variant="secondary"
                    disabled={
                      resolveMutation.isPending &&
                      resolveMutation.variables === conflict.conflict_id
                    }
                    onClick={() => resolveMutation.mutate(conflict.conflict_id)}
                  >
                    Resolve
                  </Button>
                </div>
              ))}
            </div>
          </div>
        )}

        {showEmptyState && (
          <EmptyState
            title="No reminders yet"
            subtitle="Approve a record with an explicit due date."
          />
        )}

        {sortedReminders.length > 0 && (
          <div className="pp-reminders-panel__list">
            {sortedReminders.map((rem) => (
              <div key={rem.reminder_id} className="pp-reminders-panel__reminder">
                <div className="pp-reminders-panel__reminder-head">
                  <div className="pp-reminders-panel__reminder-heading">
                    <span className="pp-reminders-panel__reminder-name">
                      {reminderName(rem.label)}
                    </span>
                    <Tag tone="lavender">{humanize(rem.record_type)}</Tag>
                  </div>
                  <DotBadge
                    label={CARE_STATUS_LABELS[rem.care_status]}
                    color={CARE_STATUS_COLORS[rem.care_status]}
                  />
                </div>

                <div className="pp-reminders-panel__reminder-meta">
                  <div className="pp-reminders-panel__meta-item">
                    <span className="pp-reminders-panel__meta-label">Due date</span>
                    <span className="pp-reminders-panel__meta-value">
                      {formatDate(rem.due_date)}
                    </span>
                  </div>
                  <div className="pp-reminders-panel__meta-item">
                    <span className="pp-reminders-panel__meta-label">Care status</span>
                    <span className="pp-reminders-panel__meta-value">
                      {relativeDueText(rem.due_date)}
                    </span>
                  </div>
                  <div className="pp-reminders-panel__meta-item">
                    <span className="pp-reminders-panel__meta-label">Reminder alerts</span>
                    <span className="pp-reminders-panel__meta-value">
                      {formatOffsets(rem.offsets_days)}
                    </span>
                  </div>
                </div>

                {rem.source?.supporting_text && (
                  <details className="pp-reminders-panel__excerpt">
                    <summary>Source excerpt</summary>
                    <p>&ldquo;{rem.source.supporting_text}&rdquo;</p>
                  </details>
                )}
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}
