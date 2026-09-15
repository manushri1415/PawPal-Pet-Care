import './OwnerKeyGate.css';
import { useId, useState } from 'react';
import type { ChangeEvent, FormEvent } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { clearOwnerKey, hasOwnerKey, setOwnerKey } from '../../lib/ownerKey';
import { Button } from '../../components/Button';
import { Card } from '../../components/Card';
import { DotBadge } from '../../components/DotBadge';
import { useSession } from '../session/SessionGate';

/**
 * Says which AI this page's extraction and Ask run on, and lets the owner
 * switch to their own space.
 *
 * Not a gate for visitors: everything on the Health Records page works without
 * a key, on PawPal's free rule-based extractor. The owner key opens the
 * persistent owner space, where the same features run on Claude (when the
 * server is configured for it). It stays collapsed to one quiet row until
 * someone asks for the key field.
 */
export function OwnerKeyGate() {
  const inputId = useId();
  const queryClient = useQueryClient();
  const session = useSession();

  // Mirrors sessionStorage, read once on mount — this is the only writer.
  const [keyIsSet, setKeyIsSet] = useState(() => hasOwnerKey());
  const [isEditing, setIsEditing] = useState(false);
  const [inputValue, setInputValue] = useState('');

  // The key selects which space every request reads and writes, so every
  // cached query belongs to the old one the moment it changes. Resetting
  // refetches the session first (SessionGate), which reports a rejected key.
  function switchSpace() {
    queryClient.resetQueries();
  }

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

  function handleCancel() {
    setInputValue('');
    setIsEditing(false);
  }

  function handleClear() {
    clearOwnerKey();
    setInputValue('');
    setKeyIsSet(false);
    setIsEditing(false);
    switchSpace();
  }

  const usesClaude = session.data?.ai_provider === 'claude';
  const badge = keyIsSet
    ? { label: usesClaude ? 'Owner space · Claude' : 'Owner space', color: 'var(--pp-sage)' }
    : { label: 'Free demo AI', color: 'var(--pp-plum)' };
  const hint = keyIsSet
    ? usesClaude
      ? 'Extraction and Ask use Claude.'
      : 'Extraction and Ask use the rule-based extractor — Claude is not configured on this server.'
    : 'Extraction and Ask use PawPal’s free rule-based extractor. Everything works without a key.';

  return (
    <div className="pp-owner-key-gate">
      <Card tone="plain" className="pp-owner-key-gate__card">
        {isEditing ? (
          <form className="pp-owner-key-gate__form" onSubmit={handleSave}>
            <p className="pp-owner-key-gate__lead">
              Paste your owner key to switch to your persistent owner space, where extraction and
              Ask use Claude.
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
              <Button type="button" variant="secondary" onClick={handleCancel}>
                Cancel
              </Button>
            </div>
          </form>
        ) : (
          <div className="pp-owner-key-gate__status">
            <div className="pp-owner-key-gate__summary">
              <DotBadge label={badge.label} color={badge.color} />
              <span className="pp-owner-key-gate__hint">{hint}</span>
            </div>
            <div className="pp-owner-key-gate__actions">
              {keyIsSet ? (
                <>
                  <Button type="button" variant="secondary" onClick={() => setIsEditing(true)}>
                    Change key
                  </Button>
                  <Button
                    type="button"
                    variant="secondary"
                    className="pp-owner-key-gate__clear-btn"
                    onClick={handleClear}
                  >
                    Use the demo
                  </Button>
                </>
              ) : (
                <Button type="button" variant="ghost" size="sm" onClick={() => setIsEditing(true)}>
                  I have an owner key
                </Button>
              )}
            </div>
          </div>
        )}
      </Card>
    </div>
  );
}
