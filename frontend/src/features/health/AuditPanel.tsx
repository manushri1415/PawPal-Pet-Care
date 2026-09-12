import './AuditPanel.css';
import { useQuery } from '@tanstack/react-query';
import { auditTrail } from '../../api/health';
import { ApiError } from '../../api/client';
import { formatDate, formatTime } from '../../lib/datetime';
import { Alert } from '../../components/Alert';
import { Card } from '../../components/Card';
import { EmptyState } from '../../components/EmptyState';
import { Eyebrow } from '../../components/Eyebrow';

const AUDIT_LIMIT = 50;

function getErrorMessage(error: unknown): string {
  if (error instanceof ApiError && typeof error.detail === 'string') return error.detail;
  if (error instanceof Error) return error.message;
  return 'Something went wrong. Please try again.';
}

/** "record_saved" -> "Record saved" so raw event slugs read like prose. */
function humanizeEvent(event: string): string {
  const words = event.split('_').filter(Boolean);
  if (words.length === 0) return event;
  const [first, ...rest] = words;
  return [`${first.charAt(0).toUpperCase()}${first.slice(1)}`, ...rest].join(' ');
}

export function AuditPanel() {
  const auditQuery = useQuery({
    queryKey: ['health', 'audit', AUDIT_LIMIT],
    queryFn: () => auditTrail(AUDIT_LIMIT),
  });

  const entries = auditQuery.data ?? [];

  return (
    <div className="pp-audit-panel">
      <Eyebrow label="Audit" tone="sage" large />
      <Card tone="plain">
        <p className="pp-audit-panel__intro">
          Every save, approval, rejection, and reminder is logged here as a tamper-evident
          human-oversight record.
        </p>

        {auditQuery.isLoading && <p className="pp-audit-panel__status">Loading audit trail…</p>}

        {auditQuery.isError && <Alert tone="error">{getErrorMessage(auditQuery.error)}</Alert>}

        {auditQuery.isSuccess && entries.length === 0 && (
          <EmptyState
            title="No activity yet."
            subtitle="Saved records, approvals, rejections, and reminders will show up here as they happen."
          />
        )}

        {entries.length > 0 && (
          <div className="pp-audit-panel__table-wrap">
            <table className="pp-audit-panel__table">
              <thead>
                <tr>
                  <th scope="col">Time</th>
                  <th scope="col">Event</th>
                  <th scope="col">Ref</th>
                  <th scope="col">Detail</th>
                </tr>
              </thead>
              <tbody>
                {entries.map((entry) => (
                  <tr key={entry.id}>
                    <td className="pp-audit-panel__time">
                      {formatDate(entry.created_at)}
                      <span className="pp-audit-panel__time-clock">
                        {formatTime(entry.created_at)}
                      </span>
                    </td>
                    <td>{humanizeEvent(entry.event)}</td>
                    <td className="pp-audit-panel__ref">{entry.ref_id}</td>
                    <td className="pp-audit-panel__detail">{entry.detail || '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}
