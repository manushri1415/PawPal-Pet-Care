import './OwnerKeyGate.css';
import { useId, useState } from 'react';
import type { ChangeEvent, FormEvent } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { clearOwnerKey, hasOwnerKey, setOwnerKey } from '../../lib/ownerKey';
import { Button } from '../../components/Button';
import { Card } from '../../components/Card';
import { DotBadge } from '../../components/DotBadge';

export function OwnerKeyGate() {
  const inputId = useId();
  const queryClient = useQueryClient();

  // Mirrors sessionStorage, read once on mount — OwnerKeyGate is the only
  // writer of the key.
  const [keyIsSet, setKeyIsSet] = useState(() => hasOwnerKey());

  // The key selects which space every request reads and writes (the owner's
  // own, or this browser's demo sandbox), so every cached query belongs to the
  // old one the moment it changes. Resetting refetches the session first
  // (SessionGate), and a rejected key is reported there.
  function switchSpace() {
    queryClient.resetQueries();
  }
  // Starts open when no key is set yet; "Change" re-opens it later. The raw
  // key is never redisplayed once saved, so this always starts blank.
  const [isEditing, setIsEditing] = useState(() => !hasOwnerKey());
  const [inputValue, setInputValue] = useState('');

  function handleSave(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmed = inputValue.trim();
    if (!trimmed) return;
    setOwnerKey(trimmed);
    setInputValue('');
    setKeyIsSet(true);
    setIsEditing(false);
    switchSpace();
  }

  function handleChange() {
    setInputValue('');
    setIsEditing(true);
  }

  function handleCancelChange() {
    setInputValue('');
    setIsEditing(false);
  }

  function handleClear() {
    clearOwnerKey();
    setInputValue('');
    setKeyIsSet(false);
    setIsEditing(true);
    switchSpace();
  }

  return (
    <div className="pp-owner-key-gate">
      <Card tone="plain" className="pp-owner-key-gate__card">
        {isEditing ? (
          <form className="pp-owner-key-gate__form" onSubmit={handleSave}>
            <p className="pp-owner-key-gate__lead">
              Paste your PawPal owner key to open your persistent owner space and unlock document
              extraction and Ask. Without it you are in a private demo sandbox.
            </p>

            <div className="pp-owner-key-gate__row">
              <label className="pp-owner-key-gate__label" htmlFor={inputId}>
                Owner key
              </label>
              <input
                id={inputId}
                className="pp-owner-key-gate__input"
                type="password"
                autoComplete="off"
                placeholder="Paste key…"
                value={inputValue}
                onChange={(event: ChangeEvent<HTMLInputElement>) => setInputValue(event.target.value)}
              />
              <Button type="submit" variant="primary" disabled={!inputValue.trim()}>
                Save key
              </Button>
              {keyIsSet && (
                <Button type="button" variant="secondary" onClick={handleCancelChange}>
                  Cancel
                </Button>
              )}
            </div>
          </form>
        ) : (
          <div className="pp-owner-key-gate__status">
            <DotBadge label="Owner key set" color="var(--pp-sage)" />
            <div className="pp-owner-key-gate__actions">
              <Button type="button" variant="secondary" onClick={handleChange}>
                Change
              </Button>
              <Button
                type="button"
                variant="secondary"
                className="pp-owner-key-gate__clear-btn"
                onClick={handleClear}
              >
                Clear
              </Button>
            </div>
          </div>
        )}
      </Card>
    </div>
  );
}
