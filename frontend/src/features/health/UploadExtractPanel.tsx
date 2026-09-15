import './UploadExtractPanel.css';
import { useId, useRef, useState } from 'react';
import type { ChangeEvent, FormEvent, ReactNode } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { extractDocumentFromFile, extractDocumentFromText } from '../../api/health';
import { ApiError } from '../../api/client';
import { Alert } from '../../components/Alert';
import { Button } from '../../components/Button';
import { Card } from '../../components/Card';
import { Eyebrow } from '../../components/Eyebrow';
import { useSession } from '../session/SessionGate';

function megabytes(bytes: number): string {
  const mb = bytes / (1024 * 1024);
  return `${Number.isInteger(mb) ? mb : mb.toFixed(1)} MB`;
}

function getErrorMessage(error: unknown): string {
  if (error instanceof ApiError && typeof error.detail === 'string') return error.detail;
  if (error instanceof Error) return error.message;
  return 'Something went wrong. Please try again.';
}

export function UploadExtractPanel({ petId, petName }: { petId: string; petName: string }) {
  const formId = useId();
  const queryClient = useQueryClient();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [file, setFile] = useState<File | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);
  const [text, setText] = useState('');
  const maxUploadBytes = useSession().data?.max_upload_bytes;

  const mutation = useMutation({
    mutationFn: (submitted: { file: File | null; text: string }) =>
      submitted.file
        ? extractDocumentFromFile(petId, submitted.file)
        : extractDocumentFromText(petId, submitted.text),
    onSuccess: (_data, submitted) => {
      queryClient.invalidateQueries({ queryKey: ['health', 'records'] });
      // Clear only what was submitted: a file picked or text typed while the
      // extraction was running is the user's next upload, not this one.
      setFile((current) => (current === submitted.file ? null : current));
      setText((current) => (current === submitted.text ? '' : current));
      const input = fileInputRef.current;
      if (input && (input.files?.[0] ?? null) === submitted.file) input.value = '';
    },
  });

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    mutation.mutate({ file, text });
  }

  function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
    const picked = event.target.files?.[0] ?? null;
    // Refuse an oversized file here: past the hosting platform's payload
    // limit the request never reaches the server to be refused with a reason.
    if (picked && maxUploadBytes && picked.size > maxUploadBytes) {
      setFileError(`That file is ${megabytes(picked.size)}; the limit is ${megabytes(maxUploadBytes)}.`);
      setFile(null);
      event.target.value = '';
      return;
    }
    setFileError(null);
    setFile(picked);
  }

  const canSubmit = file !== null || text.trim().length > 0;
  const result = mutation.data?.result;
  const isFatal = result
    ? Boolean(result.fatal_error) || (result.errors.length > 0 && result.records.length === 0)
    : false;
  const petNameMismatch =
    result?.pet_name_in_document &&
    result.pet_name_in_document.toLowerCase() !== petName.toLowerCase()
      ? result.pet_name_in_document
      : null;

  let mutationErrorAlert: ReactNode = null;
  if (mutation.isError) {
    const error = mutation.error;
    if (error instanceof ApiError && error.status === 401) {
      mutationErrorAlert = (
        <Alert tone="warning">Your owner key was not accepted. Clear it above to keep using the demo.</Alert>
      );
    } else {
      mutationErrorAlert = <Alert tone="error">{getErrorMessage(error)}</Alert>;
    }
  }

  return (
    <div className="pp-upload-extract">
      <Eyebrow label="Upload & extract" tone="lavender" large />

      <Card tone="plain">
        <form className="pp-upload-extract__form" onSubmit={handleSubmit}>
          <div className="pp-upload-extract__field">
            <label htmlFor={`${formId}-file`}>Upload PDF / DOCX / TXT</label>
            <input
              id={`${formId}-file`}
              ref={fileInputRef}
              type="file"
              accept=".pdf,.docx,.txt"
              onChange={handleFileChange}
            />
            {fileError && <Alert tone="warning">{fileError}</Alert>}
          </div>

          <div className="pp-upload-extract__divider">or</div>

          <div className="pp-upload-extract__field">
            <label htmlFor={`${formId}-text`}>Paste veterinary text</label>
            <textarea
              id={`${formId}-text`}
              rows={6}
              placeholder="Paste vaccination, medication, or appointment text here…"
              value={text}
              onChange={(event) => setText(event.target.value)}
            />
          </div>

          <p className="pp-upload-extract__hint">
            If both a file and pasted text are provided, the uploaded file is used.
          </p>

          <div className="pp-upload-extract__actions">
            <Button type="submit" variant="primary" disabled={mutation.isPending || !canSubmit}>
              {mutation.isPending ? 'Extracting…' : 'Extract records'}
            </Button>
          </div>
        </form>

        {mutationErrorAlert}

        {result && (
          <div className="pp-upload-extract__results">
            {result.injection_flagged && (
              <Alert tone="warning">
                This document contains prompt-injection-like text. It is treated as untrusted
                data — any embedded instructions are ignored, and you still review everything
                before it is saved.
              </Alert>
            )}

            {isFatal ? (
              <Alert tone="error">
                Extraction failed: {result.fatal_error ?? result.errors.join(' ')}
              </Alert>
            ) : (
              <>
                {result.records.length > 0 ? (
                  <Alert tone="success">
                    Extracted {result.records.length} record{result.records.length === 1 ? '' : 's'}{' '}
                    in {result.attempts} attempt{result.attempts === 1 ? '' : 's'}. Review them in
                    the Review tab.
                  </Alert>
                ) : (
                  <Alert tone="warning">
                    Read the document, but did not find any supported vaccination, medication, or
                    appointment records.
                  </Alert>
                )}

                {petNameMismatch && (
                  <Alert tone="warning">
                    The document names <strong>{petNameMismatch}</strong>, but the active pet is{' '}
                    <strong>{petName}</strong>. Double check this is the right pet.
                  </Alert>
                )}

                {result.missing_fields.length > 0 && (
                  <Alert tone="info">
                    Missing important fields (left blank, not guessed):{' '}
                    {result.missing_fields.join(', ')}
                  </Alert>
                )}

                {result.unsupported_fields.length > 0 && (
                  <Alert tone="info">
                    Dropped unsupported values (not grounded in the text):{' '}
                    {result.unsupported_fields.join(', ')}
                  </Alert>
                )}
              </>
            )}
          </div>
        )}
      </Card>
    </div>
  );
}
