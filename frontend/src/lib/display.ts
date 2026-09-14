/**
 * Display-only helpers for the dashboard: labels, tones and short phrasing
 * derived from API data. Nothing here feeds back into a request.
 */

import type { Category, Frequency, PetRead, Priority } from '../api/types';

export type Tone = 'plum' | 'sage' | 'peach' | 'brown' | 'ochre' | 'terracotta';

export type PetKind = 'cat' | 'dog' | 'other';

/** Coarse species bucket — picks the avatar artwork slot (`avatar-cat` etc.) and the tone. */
export function petKind(pet: Pick<PetRead, 'pet_type'>): PetKind {
  const type = pet.pet_type.trim().toLowerCase();
  if (type.includes('cat') || type.includes('kitten')) return 'cat';
  if (type.includes('dog') || type.includes('pupp')) return 'dog';
  return 'other';
}

/** Avatar tone for a pet, by species where we recognise it, else stable by name. */
export function petTone(pet: Pick<PetRead, 'pet_type' | 'name'>): Tone {
  const kind = petKind(pet);
  if (kind === 'cat') return 'plum';
  if (kind === 'dog') return 'peach';
  const type = pet.pet_type.trim().toLowerCase();
  if (['rabbit', 'bunny', 'hamster', 'guinea', 'reptile', 'turtle'].some((k) => type.includes(k))) return 'sage';
  if (['bird', 'parrot', 'fish'].some((k) => type.includes(k))) return 'brown';
  const fallback: Tone[] = ['sage', 'brown', 'plum', 'peach'];
  let hash = 0;
  for (const ch of pet.name) hash = (hash * 31 + ch.charCodeAt(0)) >>> 0;
  return fallback[hash % fallback.length];
}

export function capitalize(value: string): string {
  return value ? value.charAt(0).toUpperCase() + value.slice(1) : value;
}

/** "1 yr 4 mo", "8 mo", "Newborn". */
export function petAgeLabel(pet: Pick<PetRead, 'age' | 'age_months'>): string {
  const parts: string[] = [];
  if (pet.age > 0) parts.push(`${pet.age} yr`);
  if (pet.age_months > 0) parts.push(`${pet.age_months} mo`);
  return parts.length > 0 ? parts.join(' ') : 'Under a month';
}

export const CATEGORY_LABELS: Record<Category, string> = {
  feeding: 'Feeding',
  exercise: 'Exercise',
  grooming: 'Grooming',
  medication: 'Medication',
  enrichment: 'Enrichment',
  play: 'Play',
  training: 'Training',
};

export const CATEGORY_TONES: Record<Category, Tone> = {
  feeding: 'peach',
  exercise: 'sage',
  grooming: 'plum',
  medication: 'terracotta',
  enrichment: 'ochre',
  play: 'ochre',
  training: 'brown',
};

export const PRIORITY_LABELS: Record<Priority, string> = {
  high: 'High',
  medium: 'Medium',
  low: 'Low',
};

export const FREQUENCY_LABELS: Record<Frequency, string> = {
  once: 'One-time',
  daily: 'Daily',
  weekly: 'Weekly',
  monthly: 'Monthly',
  as_needed: 'As needed',
};

/** "45 min", "1 hr", "1 hr 30 min". */
export function durationLabel(minutes: number): string {
  if (minutes < 60) return `${minutes} min`;
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  return rest ? `${hours} hr ${rest} min` : `${hours} hr`;
}

export function greetingFor(date: Date): string {
  const hour = date.getHours();
  if (hour < 12) return 'Good morning';
  if (hour < 18) return 'Good afternoon';
  return 'Good evening';
}

/** "Nala", "Nala and Milo", "Nala, Milo and Pip". */
export function joinNames(names: string[]): string {
  if (names.length <= 1) return names[0] ?? '';
  return `${names.slice(0, -1).join(', ')} and ${names[names.length - 1]}`;
}
