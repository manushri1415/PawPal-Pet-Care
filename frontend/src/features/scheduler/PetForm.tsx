import './PetForm.css';
import { useId, useState } from 'react';
import type { ChangeEvent, FormEvent } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { createPet, updatePet } from '../../api/scheduler';
import { GENDER_OPTIONS } from '../../api/types';
import type { Gender, PetRead } from '../../api/types';
import { Alert } from '../../components/Alert';
import { Button } from '../../components/Button';

export function PetForm({
  pet,
  onDone,
  onCancel,
}: {
  pet?: PetRead;
  onDone: () => void;
  onCancel: () => void;
}) {
  const isEditing = pet !== undefined;
  const formId = useId();
  const queryClient = useQueryClient();

  const [name, setName] = useState(pet?.name ?? '');
  const [petType, setPetType] = useState(pet?.pet_type ?? '');
  const [age, setAge] = useState(pet?.age ?? 0);
  const [ageMonths, setAgeMonths] = useState(pet?.age_months ?? 0);
  const [gender, setGender] = useState<Gender>(pet?.gender ?? 'unknown');
  const [color, setColor] = useState(pet?.color ?? '');

  const mutation = useMutation({
    mutationFn: () => {
      const payload = {
        name,
        pet_type: petType,
        age,
        age_months: ageMonths,
        gender,
        color,
      };
      return isEditing && pet ? updatePet(pet.pet_id, payload) : createPet(payload);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['pets'] });
      onDone();
    },
  });

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    mutation.mutate();
  }

  return (
    <form className="pp-pet-form" onSubmit={handleSubmit}>
      <div className="pp-pet-form__title">{isEditing ? 'Edit pet' : 'Add a pet'}</div>

      <div className="pp-pet-form__grid">
        <div>
          <label htmlFor={`${formId}-name`}>Name</label>
          <input
            id={`${formId}-name`}
            type="text"
            required
            value={name}
            onChange={(event: ChangeEvent<HTMLInputElement>) => setName(event.target.value)}
          />
        </div>

        <div>
          <label htmlFor={`${formId}-type`}>Type</label>
          <input
            id={`${formId}-type`}
            type="text"
            required
            placeholder="Dog, Cat, …"
            value={petType}
            onChange={(event: ChangeEvent<HTMLInputElement>) => setPetType(event.target.value)}
          />
        </div>

        <div>
          <label htmlFor={`${formId}-age`}>Age (years)</label>
          <input
            id={`${formId}-age`}
            type="number"
            min={0}
            required
            value={age}
            onChange={(event: ChangeEvent<HTMLInputElement>) =>
              setAge(event.target.value === '' ? 0 : Number(event.target.value))
            }
          />
        </div>

        <div>
          <label htmlFor={`${formId}-age-months`}>Age (months)</label>
          <input
            id={`${formId}-age-months`}
            type="number"
            min={0}
            value={ageMonths}
            onChange={(event: ChangeEvent<HTMLInputElement>) =>
              setAgeMonths(event.target.value === '' ? 0 : Number(event.target.value))
            }
          />
        </div>

        <div>
          <label htmlFor={`${formId}-gender`}>Gender</label>
          <select
            id={`${formId}-gender`}
            value={gender}
            onChange={(event: ChangeEvent<HTMLSelectElement>) => setGender(event.target.value as Gender)}
          >
            {GENDER_OPTIONS.map((option) => (
              <option key={option} value={option}>
                {option.charAt(0).toUpperCase() + option.slice(1)}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label htmlFor={`${formId}-color`}>Color</label>
          <input
            id={`${formId}-color`}
            type="text"
            value={color}
            onChange={(event: ChangeEvent<HTMLInputElement>) => setColor(event.target.value)}
          />
        </div>
      </div>

      {mutation.isError && (
        <Alert tone="error">
          {mutation.error instanceof Error ? mutation.error.message : 'Something went wrong saving this pet.'}
        </Alert>
      )}

      <div className="pp-pet-form__actions">
        <Button type="submit" variant="primary" disabled={mutation.isPending}>
          {isEditing ? 'Save changes' : 'Add pet'}
        </Button>
        <Button type="button" variant="secondary" onClick={onCancel} disabled={mutation.isPending}>
          Cancel
        </Button>
      </div>
    </form>
  );
}
