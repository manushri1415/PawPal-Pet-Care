import './AskPanel.css';
import { useId, useState } from 'react';
import type { ChangeEvent, FormEvent, ReactNode } from 'react';
import { useMutation } from '@tanstack/react-query';
import { ask } from '../../api/health';
import { ApiError } from '../../api/client';
import { Alert } from '../../components/Alert';
import { Button } from '../../components/Button';
import { Card } from '../../components/Card';
import { Eyebrow } from '../../components/Eyebrow';

function getErrorMessage(error: unknown): string {
  if (error instanceof ApiError && typeof error.detail === 'string') return error.detail;
  if (error instanceof Error) return error.message;
  return 'Something went wrong. Please try again.';
}

/** AI-gate errors (see MIGRATION_PLAN.md §4) get a dedicated inline message
 * instead of the raw backend text — everything else falls back to the
 * generic error surface. */
function renderMutationError(error: unknown): ReactNode {
  if (error instanceof ApiError) {
    if (error.status === 401) {
      return (
        <Alert tone="warning">
          Enter your owner key above to ask questions about this pet&rsquo;s records.
        </Alert>
      );
    }
    if (error.status === 503) {
      return <Alert tone="error">AI features aren&rsquo;t configured on this server.</Alert>;
    }
  }
  return <Alert tone="error">{getErrorMessage(error)}</Alert>;
}

export function AskPanel({ petId, petName }: { petId: string; petName: string }) {
  const fieldId = useId();
  const [question, setQuestion] = useState('');

  const mutation = useMutation({
    mutationFn: (q: string) => ask(petId, { question: q, document_id: null }),
  });

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmed = question.trim();
    if (!trimmed) return;
    mutation.mutate(trimmed);
  }

  const answer = mutation.data;
  const canAsk = question.trim().length > 0 && !mutation.isPending;

  return (
    <div className="pp-ask-panel">
      <Eyebrow label="Ask" tone="lavender" large />

      <Card tone="plain">
        <h3 className="pp-ask-panel__title">Ask about {petName}&rsquo;s records</h3>
        <p className="pp-ask-panel__caption">
          Answers are grounded only in your uploaded documents, with citations.
          Medical-advice questions are refused.
        </p>

        <form className="pp-ask-panel__form" onSubmit={handleSubmit}>
          <label htmlFor={`${fieldId}-question`}>Your question</label>
          <div className="pp-ask-panel__row">
            <input
              id={`${fieldId}-question`}
              type="text"
              placeholder="When is the rabies vaccine due?"
              value={question}
              onChange={(event: ChangeEvent<HTMLInputElement>) => setQuestion(event.target.value)}
            />
            <Button type="submit" variant="primary" disabled={!canAsk}>
              {mutation.isPending ? 'Asking…' : 'Ask'}
            </Button>
          </div>
        </form>

        {mutation.isError && (
          <div className="pp-ask-panel__error">{renderMutationError(mutation.error)}</div>
        )}

        {answer && !mutation.isError && (
          <div className="pp-ask-panel__result">
            {answer.refused ? (
              <Alert tone="error">{answer.answer}</Alert>
            ) : answer.abstained ? (
              <Alert tone="warning">{answer.answer}</Alert>
            ) : (
              <p className="pp-ask-panel__answer">
                <strong>Answer:</strong> {answer.answer}
              </p>
            )}

            {answer.citations.length > 0 && (
              <div className="pp-ask-panel__sources">
                <div className="pp-ask-panel__sources-title">
                  Sources ({answer.citations.length})
                </div>
                <ol className="pp-ask-panel__citations">
                  {answer.citations.map((citation, index) => (
                    <li key={`${citation.document_id}-${citation.chunk_id}`} className="pp-ask-panel__citation">
                      <div className="pp-ask-panel__citation-label">Source {index + 1}</div>
                      <div className="pp-ask-panel__citation-section">
                        {citation.section || 'record excerpt'}
                      </div>
                      <blockquote className="pp-ask-panel__citation-text">
                        &ldquo;{citation.supporting_text}&rdquo;
                      </blockquote>
                    </li>
                  ))}
                </ol>
              </div>
            )}
          </div>
        )}
      </Card>
    </div>
  );
}
