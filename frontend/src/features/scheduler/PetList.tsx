import './PetList.css';
import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { deletePet, listPets, listTasks } from '../../api/scheduler';
import { ApiError } from '../../api/client';
import { Alert } from '../../components/Alert';
import { Button } from '../../components/Button';
import { EmptyState } from '../../components/EmptyState';
import { PlusIcon } from '../../components/icons';
import { PetArt } from '../../components/PetArt';
import { SectionHeading } from '../../components/SectionHeading';
import { AddPetCard, PetCard } from './PetCard';
import type { PetDeleteIssue } from './PetCard';
import { PetForm } from './PetForm';

interface DeleteIssue extends PetDeleteIssue {
  petId: string;
}

export function PetList() {
  const queryClient = useQueryClient();
  const petsQuery = useQuery({ queryKey: ['pets'], queryFn: listPets });
  // Shares TaskList's default open-tasks cache entry; used only for per-pet counts.
  const openTasksQuery = useQuery({
    queryKey: ['tasks', { petId: undefined, status: 'open', sort: undefined }],
    queryFn: () => listTasks({ petId: undefined, status: 'open', sort: undefined }),
  });

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
  const openCountByPet = new Map<string, number>();
  for (const task of openTasksQuery.data ?? []) {
    if (task.pet_id) openCountByPet.set(task.pet_id, (openCountByPet.get(task.pet_id) ?? 0) + 1);
  }

  const description =
    pets.length > 0
      ? `${pets.length} ${pets.length === 1 ? 'companion' : 'companions'} in your care`
      : 'Profiles for everyone you look after';

  function startAdding() {
    setEditingPetId(null);
    setIsAdding(true);
  }

  return (
    <section className="pp-pets" aria-labelledby="pp-pets-heading">
      <div className="pp-pets__head">
        <SectionHeading id="pp-pets-heading" title="Your pets" description={description} />
        {/* On the top edge of the first row of cards — only once there are pets to watch. */}
        {pets.length > 0 && <PetArt slot="pets-peek" className="pp-pets__peek" />}
      </div>

      {petsQuery.isLoading && (
        <div className="pp-pets__grid" aria-label="Loading pets">
          <div className="pp-skeleton pp-pets__skeleton" />
          <div className="pp-skeleton pp-pets__skeleton" />
        </div>
      )}

      {petsQuery.isError && (
        <Alert tone="error">
          {petsQuery.error instanceof Error ? petsQuery.error.message : 'Failed to load pets.'}
        </Alert>
      )}

      {petsQuery.isSuccess && pets.length === 0 && !isAdding && (
        <EmptyState
          className="pp-pets__empty"
          art={['empty-pets', 'empty-state']}
          title="No pets yet"
          subtitle="Add your first companion to start planning their care."
          action={
            <Button variant="primary" onClick={startAdding}>
              <PlusIcon />
              Add a pet
            </Button>
          }
        />
      )}

      {petsQuery.isSuccess && (pets.length > 0 || isAdding) && (
        <div className="pp-pets__grid">
          {pets.map((pet) => {
            if (editingPetId === pet.pet_id) {
              return (
                <div key={pet.pet_id} className="pp-pets__form-slot">
                  <PetForm pet={pet} onDone={() => setEditingPetId(null)} onCancel={() => setEditingPetId(null)} />
                </div>
              );
            }

            const isDeletingThis = deleteMutation.isPending && deleteMutation.variables?.petId === pet.pet_id;
            return (
              <PetCard
                key={pet.pet_id}
                pet={pet}
                openTaskCount={openTasksQuery.isSuccess ? (openCountByPet.get(pet.pet_id) ?? 0) : undefined}
                isDeleting={isDeletingThis}
                issue={deleteIssue?.petId === pet.pet_id ? deleteIssue : null}
                onEdit={() => {
                  setIsAdding(false);
                  setEditingPetId(pet.pet_id);
                }}
                onDelete={() => deleteMutation.mutate({ petId: pet.pet_id })}
                onForceDelete={() => deleteMutation.mutate({ petId: pet.pet_id, force: true })}
              />
            );
          })}

          {isAdding ? (
            <div className="pp-pets__form-slot">
              <PetForm onDone={() => setIsAdding(false)} onCancel={() => setIsAdding(false)} />
            </div>
          ) : (
            <AddPetCard onClick={startAdding} />
          )}
        </div>
      )}
    </section>
  );
}
