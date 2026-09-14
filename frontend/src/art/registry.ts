/**
 * Illustration registry — the one place that says which artwork goes in which
 * prepared slot on the page. Every slot below already exists in the UI; a
 * slot with no entry here simply renders nothing (no placeholder box), so the
 * app looks finished with an empty registry.
 *
 * To add artwork:
 *   1. Drop the file(s) under src/assets/ (see src/assets/README.md).
 *   2. Import them at the top of this file.
 *   3. Add an entry for the slot. Done — no component changes needed.
 *
 * Frame-swap animation: export several frames from Canva at the *same canvas
 * size* (e.g. cat-open.svg + cat-wink.svg, or dog-sleep-1z/2z/3z). Put the
 * resting frame in `src` and the rest in `frames`; the animation only ever
 * changes each frame's opacity, never anything inside an SVG. Reduced-motion
 * users see `src` alone.
 */

// import catPeekTop from '../assets/pets/cats/cat-peek-top.svg';
// import catPeekTopWink from '../assets/pets/cats/cat-peek-top-wink.svg';
// import dogSleep1 from '../assets/pets/dogs/dog-sleep-1z.svg';
// import dogSleep2 from '../assets/pets/dogs/dog-sleep-2z.svg';
// import dogSleep3 from '../assets/pets/dogs/dog-sleep-3z.svg';

/** Where artwork can appear. Each name is wired to a fixed spot in the UI. */
export type ArtSlot =
  /** Small motif on the greeting band's top-right edge (DashboardGreeting). */
  | 'greeting-motif'
  /** Cat peeking over (or from beside) the top edge of the pets grid (PetList). */
  | 'pets-peek'
  /** Small motif inside the "Add a pet" card, above the plus button (PetCard). */
  | 'add-pet-motif'
  /** Tiny illustration on the schedule card's top-right corner (ScheduleView). */
  | 'schedule-corner'
  /** Default illustration for every empty state (EmptyState). */
  | 'empty-state'
  /** Per-section overrides; each falls back to 'empty-state'. */
  | 'empty-pets'
  | 'empty-schedule'
  | 'empty-tasks'
  /** Pet portraits by species, used inside every PetAvatar circle. */
  | 'avatar-cat'
  | 'avatar-dog'
  | 'avatar-other';

/** How the wrapper sits in the layout. Each slot has a sensible default. */
export type ArtVariant =
  /** Absolutely positioned, bottom edge tucked behind the content below it. */
  | 'peek-top'
  /** Absolutely positioned, hanging off the right edge of its section. */
  | 'peek-side'
  /** In-flow, centered block inside an EmptyState. */
  | 'empty-state'
  /** Absolutely positioned ornament; the slot's CSS sets where. */
  | 'decoration'
  /** In-flow inline block (icons, avatars). */
  | 'inline';

export type ArtAnimation =
  /** `frames[0]` snaps over `src` for ~180 ms once per `period` (default 7 s). */
  | 'wink'
  /** `src` then each frame in turn, soft cross-fades, one cycle per `period` (default 4.5 s). */
  | 'sleep'
  /** Whole illustration nudges a few px out of hiding once per `period` (default 11 s). */
  | 'peek'
  /** 1.5 px idle rise-and-fall, continuous. */
  | 'breathe'
  /** Fades in when it first appears. */
  | 'fade';

export interface ArtSpec {
  /** Resting frame. The only thing reduced-motion users ever see. */
  src: string;
  /** Extra frames exported at exactly the same canvas size as `src`. */
  frames?: string[];
  /** Intrinsic size in CSS px — fixes the aspect ratio so nothing shifts while loading. */
  width: number;
  height: number;
  /** Overrides the slot's default placement. */
  variant?: ArtVariant;
  animations?: ArtAnimation[];
  /** Seconds per wink / sleep cycle / peek. */
  period?: number;
  /** Seconds to offset the start, so several instances don't move in lockstep. */
  delay?: number;
  /** Set only when the picture carries meaning; leave unset for decoration. */
  alt?: string;
}

export const ART: Partial<Record<ArtSlot, ArtSpec>> = {
  // 'pets-peek': {
  //   src: catPeekTop,
  //   frames: [catPeekTopWink],
  //   width: 128,
  //   height: 72,
  //   animations: ['wink', 'peek'],
  // },
  // 'empty-state': {
  //   src: dogSleep1,
  //   frames: [dogSleep2, dogSleep3],
  //   width: 160,
  //   height: 96,
  //   animations: ['sleep', 'breathe'],
  // },
};

export const DEFAULT_VARIANT: Record<ArtSlot, ArtVariant> = {
  'greeting-motif': 'decoration',
  'pets-peek': 'peek-top',
  'add-pet-motif': 'inline',
  'schedule-corner': 'decoration',
  'empty-state': 'empty-state',
  'empty-pets': 'empty-state',
  'empty-schedule': 'empty-state',
  'empty-tasks': 'empty-state',
  'avatar-cat': 'inline',
  'avatar-dog': 'inline',
  'avatar-other': 'inline',
};

/** First registered slot wins, so callers can pass `['empty-pets', 'empty-state']`. */
export function resolveArt(
  slot: ArtSlot | ArtSlot[],
): { slot: ArtSlot; spec: ArtSpec } | undefined {
  for (const candidate of Array.isArray(slot) ? slot : [slot]) {
    const spec = ART[candidate];
    if (spec) return { slot: candidate, spec };
  }
  return undefined;
}
