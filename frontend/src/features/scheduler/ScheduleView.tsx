import './ScheduleView.css';
import { useEffect, useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { Card } from '../../components/Card';
import { Eyebrow } from '../../components/Eyebrow';
import { Alert } from '../../components/Alert';
import { Button } from '../../components/Button';
import { DotBadge, PRIORITY_COLORS } from '../../components/DotBadge';
import { generateSchedule } from '../../api/scheduler';
import { formatTime } from '../../lib/datetime';

export function ScheduleView() {
  const [date, setDate] = useState('');
  const mutation = useMutation({
    mutationFn: () => generateSchedule(date || undefined),
  });

  useEffect(() => {
    mutation.mutate();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <section className="pp-schedule-view">
      <Eyebrow label="Today's Schedule" tone="sage" large />
      <Card tone="sage" ruled>
        <div className="pp-schedule-view-controls">
          <input
            type="date"
            value={date}
            onChange={(event) => setDate(event.target.value)}
            aria-label="Schedule date"
          />
          <Button variant="primary" onClick={() => mutation.mutate()}>
            Generate
          </Button>
        </div>

        {mutation.isPending && <p className="pp-schedule-view-quiet">Generating schedule…</p>}

        {mutation.isError && <Alert tone="error">{mutation.error.message}</Alert>}

        {mutation.isSuccess && (
          <>
            {mutation.data.schedule.length === 0 ? (
              <p className="pp-schedule-view-quiet">Nothing scheduled.</p>
            ) : (
              <ul className="pp-schedule-view-list">
                {mutation.data.schedule.map((item) => (
                  <li key={item.task.task_id} className="pp-schedule-view-row">
                    <span className="pp-schedule-view-time">
                      {formatTime(item.start)}–{formatTime(item.end)}
                    </span>
                    <span className="pp-schedule-view-name">{item.task.name}</span>
                    <DotBadge label={item.task.priority} color={PRIORITY_COLORS[item.task.priority]} />
                  </li>
                ))}
              </ul>
            )}

            {mutation.data.conflicts.length > 0 && (
              <div className="pp-schedule-view-conflicts">
                <Alert tone="warning">
                  <p className="pp-schedule-view-conflicts-heading">Conflicts</p>
                  <ul className="pp-schedule-view-list">
                    {mutation.data.conflicts.map((conflict) => (
                      <li key={conflict}>{conflict}</li>
                    ))}
                  </ul>
                </Alert>
              </div>
            )}
          </>
        )}
      </Card>
    </section>
  );
}
