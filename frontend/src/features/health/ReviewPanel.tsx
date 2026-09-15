import './ReviewPanel.css';
import { useId, useState } from 'react';
import type { ChangeEvent, FormEvent } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { approveRecord, listRecords, rejectRecord, updateRecord } from '../../api/health';
import { ApiError } from '../../api/client';
import { formatDate } from '../../lib/datetime';
import type { HealthRecord } from '../../api/types';
import { Alert } from '../../components/Alert';
import { Button } from '../../components/Button';
import { Card } from '../../components/Card';
import { CARE_STATUS_COLORS, CARE_STATUS_LABELS, DotBadge } from '../../components/DotBadge';
import { EmptyState } from '../../components/EmptyState';
import { Eyebrow } from '../../components/Eyebrow';
import { Tag } from '../../components/Tag';

// Copied verbatim from the old pages/1_Health_Records.py `_FIELD_LABELS` /
// `_FIELD_ORDER` maps — the exact display order/label mapping the Streamlit
// page used for approved records.
const FIELD_LABELS: Record<string, string> = {
  vaccine_name: 'Vaccine',
  administered_date: 'Given',
  due_date: 'Due',
  medication_name: 'Medication',
  dosage: 'Dosage',
  frequency: 'Frequency',
  duration: 'Duration',
  purpose: 'Purpose',
  appointment_date: 'Appointment',
  clinic: 'Clinic',
  veterinarian: 'Veterinarian',
};

const FIELD_ORDER: Record<string, string[]> = {
  vaccination: ['vaccine_name', 'administered_date', 'due_date', 'clinic', 'veterinarian'],
  medication: ['medication_name', 'dosage', 'frequency', 'duration', 'clinic'],
  appointment: ['purpose', 'appointment_date', 'clinic'],
};

function fieldLabel(fieldName: string): string {
  return FIELD_LABELS[fieldName] ?? fieldName;
}

function recordName(record: HealthRecord): string {
  return record.fields.vaccine_name || record.fields.medication_name || record.fields.purpose || 'Record';
}

/** Non-empty fields for an approved record, in the field/label map's order,
 * with any leftover fields appended — mirrors the old page's `_ordered_fields`. */
function orderedFields(record: HealthRecord): [string, string][] {
  const present = Object.entries(record.fields).filter(
    (entry): entry is [string, string] => entry[1] !== null && entry[1] !== '',
  );
  const byName = new Map(present);
  const order = FIELD_ORDER[record.record_type] ?? [];
  const first = order.filter((name) => byName.has(name)).map((name): [string, string] => [name, byName.get(name) as string]);
  const seen = new Set(order);
  const rest = present.filter(([name]) => !seen.has(name));
  return [...first, ...rest];
}

/** Date-named fields get the same compact "Jan 5, 2026" formatting the
 * reminders panel uses; every other field renders as-is — mirrors the old
 * page's `_format_field_value`, which only reformatted date fields. */
function formatFieldValue(fieldName: string, value: string): string {
  if (fieldName.toLowerCase().includes('date')) {
    const formatted = formatDate(value);
    if (formatted) return formatted;
  }
  return value;
}

function getErrorMessage(error: unknown): string {
  if (error instanceof ApiError && typeof error.detail === 'string') return error.detail;
  if (error instanceof Error) return error.message;
  return 'Something went wrong. Please try again.';
}

function EditFieldForm({
  record,
  onDone,
  onCancel,
}: {
  record: HealthRecord;
  onDone: () => void;
  onCancel: () => void;
}) {
  const formId = useId();
  const queryClient = useQueryClient();
  const fieldNames = Object.keys(record.fields);
  const [fieldName, setFieldName] = useState(fieldNames[0] ?? '');
  const [value, setValue] = useState(record.fields[fieldNames[0] ?? ''] ?? '');

  const mutation = useMutation({
    mutationFn: () => updateRecord(record.record_id, { fields: { [fieldName]: value || null } }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['health', 'records'] });
      onDone();
    },
  });

  function handleFieldChange(event: ChangeEvent<HTMLSelectElement>) {
    const nextField = event.target.value;
    setFieldName(nextField);
    setValue(record.fields[nextField] ?? '');
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    mutation.mutate();
  }

  return (
    <form className="pp-review-edit" onSubmit={handleSubmit}>
      <div className="pp-review-edit__grid">
        <div>
          <label htmlFor={`${formId}-field`}>Field</label>
          <select id={`${formId}-field`} value={fieldName} onChange={handleFieldChange}>
            {fieldNames.map((name) => (
              <option key={name} value={name}>
                {fieldLabel(name)}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label htmlFor={`${formId}-value`}>New value</label>
          <input
            id={`${formId}-value`}
            type="text"
            value={value}
            onChange={(event: ChangeEvent<HTMLInputElement>) => setValue(event.target.value)}
          />
        </div>
      </div>

      {mutation.isError && <Alert tone="error">{getErrorMessage(mutation.error)}</Alert>}

      <div className="pp-review-edit__actions">
        <Button type="submit" variant="primary" disabled={mutation.isPending}>
          Apply edit
        </Button>
        <Button type="button" variant="secondary" onClick={onCancel} disabled={mutation.isPending}>
          Cancel
        </Button>
      </div>
    </form>
  );
}

function PendingRecordCard({ record }: { record: HealthRecord }) {
  const queryClient = useQueryClient();
  const [isEditing, setIsEditing] = useState(false);

  const approveMutation = useMutation({
    mutationFn: () => approveRecord(record.record_id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['health', 'records'] }),
  });

  const rejectMutation = useMutation({
    mutationFn: () => rejectRecord(record.record_id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['health', 'records'] }),
  });

  const busy = approveMutation.isPending || rejectMutation.isPending;
  const reviewError = approveMutation.error ?? rejectMutation.error;

  return (
    <div className="pp-review-card">
      <div className="pp-review-card__header">
        <span className="pp-review-card__name">{recordName(record)}</span>
        <Tag tone="lavender">{record.record_type}</Tag>
        <DotBadge label={CARE_STATUS_LABELS[record.care_status]} color={CARE_STATUS_COLORS[record.care_status]} />
        <span className="pp-review-card__confidence">confidence {record.confidence}</span>
      </div>

      <ul className="pp-review-card__fields">
        {Object.entries(record.fields).map(([fname, fvalue]) => {
          const evidence = record.evidence[fname];
          return (
            <li key={fname} className="pp-review-card__field">
              <span className="pp-review-card__field-row">
                <strong>{fieldLabel(fname)}:</strong>{' '}
                {fvalue === null ? <em>not found</em> : fvalue}
                {evidence && <span className="pp-review-card__score">score {evidence.match_score}</span>}
              </span>
              {evidence && <span className="pp-review-card__evidence">&ldquo;{evidence.supporting_text}&rdquo;</span>}
            </li>
          );
        })}
      </ul>

      {reviewError !== null && reviewError !== undefined && (
        <Alert tone="error">{getErrorMessage(reviewError)}</Alert>
      )}

      <div className="pp-review-card__actions">
        <Button variant="primary" disabled={busy} onClick={() => approveMutation.mutate()}>
          Approve
        </Button>
        <Button variant="secondary" disabled={busy} onClick={() => rejectMutation.mutate()}>
          Reject
        </Button>
        <Button type="button" variant="secondary" onClick={() => setIsEditing((current) => !current)}>
          {isEditing ? 'Close' : 'Edit a field'}
        </Button>
      </div>

      {isEditing && (
        <EditFieldForm record={record} onDone={() => setIsEditing(false)} onCancel={() => setIsEditing(false)} />
      )}
    </div>
  );
}

function ApprovedRecordCard({ record }: { record: HealthRecord }) {
  const fields = orderedFields(record);
  const sourced = fields.filter(([fname]) => record.evidence[fname]);

  return (
    <div className="pp-review-approved">
      <div className="pp-review-approved__header">
        <span className="pp-review-approved__name">{recordName(record)}</span>
        <DotBadge label={CARE_STATUS_LABELS[record.care_status]} color={CARE_STATUS_COLORS[record.care_status]} />
      </div>
      <Tag tone="sage">{record.record_type}</Tag>

      {fields.length > 0 && (
        <dl className="pp-review-approved__grid">
          {fields.map(([fname, fvalue]) => (
            <div key={fname} className="pp-review-approved__field">
              <dt>{fieldLabel(fname)}</dt>
              <dd>{formatFieldValue(fname, fvalue)}</dd>
            </div>
          ))}
        </dl>
      )}

      {sourced.length > 0 && (
        <details className="pp-review-approved__sources">
          <summary>Source details</summary>
          <ul className="pp-review-approved__source-list">
            {sourced.map(([fname]) => (
              <li key={fname}>
                <strong>{fieldLabel(fname)}:</strong> &ldquo;{record.evidence[fname].supporting_text}&rdquo;
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}

export function ReviewPanel({ petId }: { petId: string }) {
  const pendingQuery = useQuery({
    queryKey: ['health', 'records', petId, 'pending'],
    queryFn: () => listRecords(petId, 'pending'),
  });
  const approvedQuery = useQuery({
    queryKey: ['health', 'records', petId, 'approved'],
    queryFn: () => listRecords(petId, 'approved'),
  });

  const pending = pendingQuery.data ?? [];
  const approved = approvedQuery.data ?? [];

  return (
    <div className="pp-review-panel">
      <Eyebrow label="Review" tone="lavender" large />

      <Card tone="plain">
        <p className="pp-review-panel__intro">
          Nothing is saved or scheduled until you approve it. Edit values inline if needed.
        </p>

        {pendingQuery.isLoading && <p className="pp-review-panel__status">Loading records…</p>}
        {pendingQuery.isError && <Alert tone="error">{getErrorMessage(pendingQuery.error)}</Alert>}

        {pendingQuery.isSuccess && pending.length === 0 && (
          <EmptyState
            title="Nothing to review"
            subtitle="No records awaiting review — extract a document in the Upload tab."
          />
        )}

        {pending.length > 0 && (
          <div className="pp-review-panel__list">
            {pending.map((record) => (
              <PendingRecordCard key={record.record_id} record={record} />
            ))}
          </div>
        )}
      </Card>

      {approvedQuery.isError && <Alert tone="error">{getErrorMessage(approvedQuery.error)}</Alert>}

      {approvedQuery.isSuccess && approved.length > 0 && (
        <div className="pp-review-panel__approved-section">
          <Eyebrow label={`Approved (${approved.length})`} tone="sage" />
          <div className="pp-review-panel__approved-grid">
            {approved.map((record) => (
              <ApprovedRecordCard key={record.record_id} record={record} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
