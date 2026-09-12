import './PetList.css';
import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { deletePet, listPets } from '../../api/scheduler';
import type { PetRead } from '../../api/types';
import { ApiError } from '../../api/client';
import { Alert } from '../../components/Alert';
import { Button } from '../../components/Button';
import { Card } from '../../components/Card';
import { EmptyState } from '../../components/EmptyState';
import { Eyebrow } from '../../components/Eyebrow';
import { Tag } from '../../components/Tag';
import { PetForm } from './PetForm';

function petMetaLine(pet: PetRead) {
  const parts = [`${pet.age}y`];
  if (pet.age_months) parts.push(`${pet.age_months}mo`);
  if (pet.gender && pet.gender !== 'unknown') parts.push(pet.gender);
  if (pet.color) parts.push(pet.color);
  return parts.join(' · ');
}

interface DeleteIssue {
  petId: string;
  tone: 'warning' | 'error';
  message: string;
}

export function PetList() {
  const queryClient = useQueryClient();
  const petsQuery = useQuery({ queryKey: ['pets'], queryFn: listPets });

  const [isAdding, setIsAdding] = useState(false);
  const [editingPetId, setEditingPetId] = useState<string | null>(null);
  const [deleteIssue, setDeleteIssue] = useState<DeleteIssue | null>(null);

  const deleteMutation = useMutation({
    mutationFn: ({ petId, force }: { petId: string; force?: boolean }) => deletePet(petId, force),
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: ['pets'] });
      queryClient.invalidateQueries({ queryKey: ['tasks'] });
      setDeleteIssue((current) => (current?.petId === variables.petId ? null : current));
    },
    onError: (error, variables) => {
      if (error instanceof ApiError && error.status === 409 && !variables.force) {
        setDeleteIssue({ petId: variables.petId, tone: 'warning', message: error.message });
      } else {
        setDeleteIssue({
          petId: variables.petId,
          tone: 'error',
          message: error instanceof Error ? error.message : 'Failed to delete this pet.',
        });
      }
    },
  });

  const pets = petsQuery.data ?? [];

  return (
    <div className="pp-pet-list">
      <Eyebrow label="Pets" tone="terracotta" large />

      <Card tone="plain">
        <div className="pp-pet-list__header">
          <Button
            variant="primary"
            onClick={() => {
              setEditingPetId(null);
              setIsAdding((current) => !current);
            }}
          >
            {isAdding ? 'Close' : 'Add pet'}
          </Button>
        </div>

        {isAdding && <PetForm onDone={() => setIsAdding(false)} onCancel={() => setIsAdding(false)} />}

        {petsQuery.isLoading && <p className="pp-pet-list__status">Loading pets…</p>}

        {petsQuery.isError && (
          <Alert tone="error">
            {petsQuery.error instanceof Error ? petsQuery.error.message : 'Failed to load pets.'}
          </Alert>
        )}

        {petsQuery.isSuccess && pets.length === 0 && (
          <EmptyState
            title="No pets yet"
            subtitle="Add your first pet to start scheduling their care."
          />
        )}

        {petsQuery.isSuccess && pets.length > 0 && (
          <div className="pp-pet-list__grid">
            {pets.map((pet) => {
              const isEditingThis = editingPetId === pet.pet_id;
              const issue = deleteIssue?.petId === pet.pet_id ? deleteIssue : null;
              const isDeletingThis =
                deleteMutation.isPending && deleteMutation.variables?.petId === pet.pet_id;

              if (isEditingThis) {
                return (
                  <PetForm
                    key={pet.pet_id}
                    pet={pet}
                    onDone={() => setEditingPetId(null)}
                    onCancel={() => setEditingPetId(null)}
                  />
                );
              }

              return (
                <div key={pet.pet_id} className="pp-pet-list__tile">
                  <div className="pp-pet-list__tile-name">{pet.name}</div>
                  <Tag>{pet.pet_type}</Tag>
                  <p className="pp-pet-list__meta">{petMetaLine(pet)}</p>

                  <div className="pp-pet-list__tile-actions">
                    <Button
                      variant="secondary"
                      onClick={() => {
                        setIsAdding(false);
                        setEditingPetId(pet.pet_id);
                      }}
                    >
                      Edit
                    </Button>
                    <Button
                      variant="secondary"
                      className="pp-pet-list__delete-btn"
                      disabled={isDeletingThis}
                      onClick={() => deleteMutation.mutate({ petId: pet.pet_id })}
                    >
                      Delete
                    </Button>
                  </div>

                  {issue && (
                    <div className="pp-pet-list__issue">
                      <Alert tone={issue.tone}>{issue.message}</Alert>
                      {issue.tone === 'warning' && (
                        <Button
                          variant="secondary"
                          disabled={isDeletingThis}
                          onClick={() => deleteMutation.mutate({ petId: pet.pet_id, force: true })}
                        >
                          Delete anyway
                        </Button>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </Card>
    </div>
  );
}
