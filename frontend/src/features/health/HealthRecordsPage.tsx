import './HealthRecordsPage.css';
import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { listPets } from '../../api/scheduler';
import { EmptyState } from '../../components/EmptyState';
import { PetArt } from '../../components/PetArt';
import { Tabs } from '../../components/Tabs';
import type { TabItem } from '../../components/Tabs';
import { OwnerKeyGate } from './OwnerKeyGate';
import { UploadExtractPanel } from './UploadExtractPanel';
import { ReviewPanel } from './ReviewPanel';
import { RemindersPanel } from './RemindersPanel';
import { AskPanel } from './AskPanel';
import { AuditPanel } from './AuditPanel';

const TABS: TabItem[] = [
  { id: 'upload', label: 'Upload & Extract' },
  { id: 'review', label: 'Review' },
  { id: 'reminders', label: 'Reminders' },
  { id: 'ask', label: 'Ask' },
  { id: 'audit', label: 'Audit' },
];

const NO_PET_SELECTED = (
  <EmptyState
    title="Select a pet"
    subtitle="Choose a pet above to see this section."
  />
);

/**
 * Composes the health-records feature components built in Phase 4. Every
 * child is fully self-contained (own React Query fetching/mutations) — this
 * component is pure layout/wiring, mirroring how SchedulerPage.tsx composes
 * the scheduler feature. See MIGRATION_PLAN.md §5.
 */
export function HealthRecordsPage() {
  const petsQuery = useQuery({ queryKey: ['pets'], queryFn: listPets });
  const pets = petsQuery.data ?? [];

  const [selectedPetId, setSelectedPetId] = useState('');
  const [activeTabId, setActiveTabId] = useState(TABS[0].id);

  // Default the selection to the first pet once pets load, mirroring how
  // RoutineForm.tsx syncs query data into local state — but only while
  // nothing has been chosen yet, so it never overrides the user's own pick.
  useEffect(() => {
    if (selectedPetId) return;
    if (pets.length > 0) setSelectedPetId(pets[0].pet_id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [petsQuery.data]);

  const selectedPet = pets.find((pet) => pet.pet_id === selectedPetId);
  const noPetsAtAll = petsQuery.isSuccess && pets.length === 0;

  return (
    <div className="pp-health-records-page">
      <div className="pp-health-records-page__head">
        <h1>Health Records</h1>
        {/* Sits on the top edge of the owner-key card below. */}
        <PetArt slot="records-peek" className="pp-health-records-page__peek" />
      </div>

      <div className="pp-section">
        <OwnerKeyGate />
      </div>

      {petsQuery.isLoading && (
        <p className="pp-health-records-page__status">Loading pets…</p>
      )}

      {noPetsAtAll && (
        <div className="pp-section">
          <EmptyState
            title="Add a pet to get started"
            subtitle={
              <>
                Health records are tracked per pet. Add one from the{' '}
                <Link to="/app">Scheduler</Link> page first.
              </>
            }
          />
        </div>
      )}

      {pets.length > 0 && (
        <>
          <div className="pp-section pp-health-records-page__pet-select">
            <label htmlFor="pp-health-pet">
              Pet
              <select
                id="pp-health-pet"
                value={selectedPetId}
                onChange={(event) => setSelectedPetId(event.target.value)}
              >
                {pets.map((pet) => (
                  <option key={pet.pet_id} value={pet.pet_id}>
                    {pet.name}
                  </option>
                ))}
              </select>
            </label>
          </div>

          <div className="pp-section">
            <Tabs items={TABS} activeId={activeTabId} onChange={setActiveTabId} />

            <div
              className="pp-health-records-page__panel"
              role="tabpanel"
              id={`panel-${activeTabId}`}
              aria-labelledby={`tab-${activeTabId}`}
            >
              {activeTabId === 'upload' &&
                (selectedPet ? (
                  <UploadExtractPanel petId={selectedPet.pet_id} petName={selectedPet.name} />
                ) : (
                  NO_PET_SELECTED
                ))}

              {activeTabId === 'review' &&
                (selectedPet ? <ReviewPanel petId={selectedPet.pet_id} /> : NO_PET_SELECTED)}

              {activeTabId === 'reminders' &&
                (selectedPet ? <RemindersPanel petId={selectedPet.pet_id} /> : NO_PET_SELECTED)}

              {activeTabId === 'ask' &&
                (selectedPet ? (
                  <AskPanel petId={selectedPet.pet_id} petName={selectedPet.name} />
                ) : (
                  NO_PET_SELECTED
                ))}

              {activeTabId === 'audit' && <AuditPanel />}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
