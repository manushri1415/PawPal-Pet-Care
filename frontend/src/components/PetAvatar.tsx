import './PetAvatar.css';
import type { PetRead } from '../api/types';
import { resolveArt } from '../art/registry';
import type { ArtSlot } from '../art/registry';
import { petKind, petTone } from '../lib/display';
import { PawIcon } from './icons';
import { PetArt } from './PetArt';

/**
 * Round pet portrait. Shows the species artwork registered for
 * `avatar-cat` / `avatar-dog` / `avatar-other` (art/registry.ts) when there is
 * one, otherwise the pet's initial on its species tone. With no pet at all
 * (a task not tied to one) it shows a quiet paw.
 */
export function PetAvatar({
  pet,
  size = 'md',
  className,
}: {
  pet?: Pick<PetRead, 'name' | 'pet_type'>;
  size?: 'xs' | 'sm' | 'md' | 'lg';
  className?: string;
}) {
  const tone = pet ? petTone(pet) : 'brown';
  const artSlot: ArtSlot | undefined = pet ? `avatar-${petKind(pet)}` : undefined;
  const hasArt = artSlot !== undefined && resolveArt(artSlot) !== undefined;
  const classes = [
    'pp-pet-avatar',
    `pp-pet-avatar--${size}`,
    `pp-tone--${tone}`,
    hasArt && 'pp-pet-avatar--art',
    className,
  ]
    .filter(Boolean)
    .join(' ');

  return (
    <span className={classes} aria-hidden="true">
      {hasArt && artSlot ? (
        <PetArt slot={artSlot} className="pp-pet-avatar__art" />
      ) : pet ? (
        pet.name.trim().charAt(0).toUpperCase() || '?'
      ) : (
        <PawIcon />
      )}
    </span>
  );
}
