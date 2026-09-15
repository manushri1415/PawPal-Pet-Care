/**
 * Illustration registry — the one place that says which artwork goes in which
 * prepared slot on the page. A slot with no entry renders nothing (no
 * placeholder box), so the app looks finished whatever is registered.
 *
 * The artwork itself lives in src/assets/pets/ (see index.ts there for the
 * frame families and their shared canvas sizes). To place a file:
 *   1. Drop it under src/assets/ (see src/assets/README.md).
 *   2. Import it (or add it to assets/pets/index.ts).
 *   3. Add or edit the slot entry below. No component changes needed.
 *
 * House rules for what goes where (the point is a cozy product with the
 * occasional character, not a page of stickers):
 *   - At most one or two decorative characters in a typical desktop viewport.
 *   - Information-dense sections (the schedule, the task list) get no
 *     decoration inside them; a peek from an edge at most.
 *   - Every illustration has a reason to be where it is (a cat watching the
 *     pets, a dog asleep because there is nothing to do yet).
 *   - Never the same illustration in two empty states on one page — so there
 *     is deliberately no page-wide 'empty-state' default; each empty state
 *     that deserves art gets its own entry, the rest stay text-only.
 *   - Not every slot needs filling. 'greeting-motif', 'schedule-corner' and
 *     'add-pet-motif' are prepared but empty; the gray peeking cat lives on
 *     the Health Records page instead of the (already illustrated) Today page.
 *   - Characters share one BEAT and take turns: each one's moment (wink,
 *     wave, tail flick) lands in the last fifth of its cycle, so different
 *     `delay`s keep them from moving at the same time.
 *
 * Two kinds of multi-file family:
 *   - `frames`: complete alternate drawings on the same canvas (cat-open +
 *     cat-wink, side-peek pose 1 + pose 2). Only one shows at a time.
 *   - `layers`: a body (`src`) that always shows, plus overlay-only files
 *     (Z's, a tail) that take turns on top of it. `still` picks the layer
 *     shown when nothing animates (reduced motion).
 * Animation only ever changes opacity, never anything inside an SVG.
 */

import { petAssets, petAssetSizes } from '../assets/pets';

/** Where artwork can appear. Each name is wired to a fixed spot in the UI. */
export type ArtSlot =
  /** Peeks over the greeting band's top edge (DashboardGreeting). Prepared, empty. */
  | 'greeting-motif'
  /** Cat on the top edge of the pets grid, paws over the first row of cards; only while there are pets (PetList). */
  | 'pets-peek'
  /** Small motif inside the "Add a pet" card, above the plus button (PetCard). Prepared, empty. */
  | 'add-pet-motif'
  /** Lounging on the schedule card's top-right edge (ScheduleView). Prepared, empty. */
  | 'schedule-corner'
  /** Peeks out from behind the right edge of the tasks panel; wide screens only (TaskList). */
  | 'tasks-peek'
  /** Cat sitting on the top edge of the owner-key card on Health Records (HealthRecordsPage). */
  | 'records-peek'
  /** Page-wide fallback for every EmptyState. Deliberately empty (see house rules). */
  | 'empty-state'
  /** Per-section empty states; each falls back to 'empty-state'. */
  | 'empty-pets'
  | 'empty-schedule'
  | 'empty-tasks'
  /** Pet portraits by species, used inside every PetAvatar circle. */
  | 'avatar-cat'
  | 'avatar-dog'
  | 'avatar-other';

/** How the wrapper sits in the layout. Each slot has a sensible default. */
export type ArtVariant =
  /** Absolutely positioned on the top edge of the content below its container: body above the edge, paws over it. */
  | 'peek-top'
  /** Absolutely positioned behind its container, hanging off the right edge. */
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
  /**
   * peek-top only. Starts out of sight below the edge, hops up onto it `delay`
   * seconds after mount, winks, drops back out of sight, and does it again
   * every `period` (default 10 s). Rendered by components/PeekingPet, so the
   * slot's CSS uses its `--peek-pet-*` knobs rather than `--pp-art-*`.
   */
  | 'hop'
  /** Layers appear one after another (Z, ZZ, ZZZ), hold, then clear; one cycle per `period` (default 6.5 s). */
  | 'sleep'
  /** Rests, then once per `period` (default 10 s) briefly shows the other frame(s) and returns — a wave, a tail flick. */
  | 'gesture'
  /** Whole illustration nudges a few px out of hiding once per `period` (default 11 s). peek-side only; peek-top art sits on an edge and must not move. */
  | 'peek'
  /** 1.5 px idle rise-and-fall, continuous. */
  | 'breathe'
  /** Eases in once its resting frame has loaded, instead of popping in. */
  | 'fade';

export interface ArtSpec {
  /** Resting frame — or, with `layers`, the body that always shows. The only thing reduced-motion users see (plus the `still` layer). */
  src: string;
  /** Complete alternate frames exported at exactly the same canvas size as `src`. */
  frames?: string[];
  /** Overlay-only files (same canvas) drawn on top of `src`; they take turns, `src` never fades. */
  layers?: string[];
  /** Index into `layers` shown when nothing animates. Default 0. */
  still?: number;
  /** Intrinsic size in CSS px — fixes the aspect ratio so nothing shifts while loading. */
  width: number;
  height: number;
  /**
   * Where the container's edge crosses the image, in the image's own units.
   * peek-top: the y where the body ends (the paws hang below it, over the edge).
   * peek-side: the x just past the wall line drawn into the frames (stays hidden).
   */
  edge?: number;
  /** Overrides the slot's default placement. */
  variant?: ArtVariant;
  animations?: ArtAnimation[];
  /** Seconds per wink / sleep cycle / gesture / peek / hop. */
  period?: number;
  /**
   * Seconds to offset the start, so several characters don't move in lockstep.
   * For `hop` it is the time of the first hop; for the others it delays the
   * start of the cycle (whose moment comes in its last fifth).
   */
  delay?: number;
  /** Set only when the picture carries meaning; leave unset for decoration. */
  alt?: string;
}

const { orangePeekCat, grayPeekCat, graySidePeekCat, sleepingDog, restingOrangeCat } = petAssets;

/** Shared cycle length for the characters that "do something" now and then. */
const BEAT = 12;
/**
 * Each character's turn within the beat (`delay` values), chosen so their
 * moments never overlap. Seconds within a 12 s cycle:
 *   orange peek cat   hops up 2.5–3.4, winks 5.1, drops 7.3–7.9 (hidden the rest)
 *   gray side cat     slides out and waves 8.4–11
 *   resting cat       tail flick 11.6–0.6
 */
const TURN = { orangePeekCat: 2.5, graySidePeekCat: 11, restingOrangeCat: 2 } as const;

export const ART: Partial<Record<ArtSlot, ArtSpec>> = {
  /* ---- Today page (populated): two decorative characters at most ---- */

  // Out of sight when the page loads; hops up onto the pet cards, winks, drops back.
  'pets-peek': {
    src: orangePeekCat.open,
    frames: [orangePeekCat.wink],
    ...petAssetSizes.orangePeekCat,
    edge: 98.396,
    animations: ['hop'],
    period: BEAT,
    delay: TURN.orangePeekCat,
  },

  // Peeking at the task list from the page margin (≥1360px only, see TaskList.css).
  'tasks-peek': {
    src: graySidePeekCat.pose1,
    frames: [graySidePeekCat.pose2],
    ...petAssetSizes.graySidePeekCat,
    edge: 18.257,
    animations: ['gesture', 'peek', 'fade'],
    period: BEAT,
    delay: TURN.graySidePeekCat,
  },

  /* ---- Today page (empty states): one illustration per empty state, none repeated ---- */

  // "No pets yet": nothing to look after, so the dog sleeps. Ambient, not on the beat.
  'empty-pets': {
    src: sleepingDog.body,
    layers: [sleepingDog.z1, sleepingDog.z2, sleepingDog.z3],
    still: 2,
    ...petAssetSizes.sleepingDog,
    animations: ['sleep', 'breathe'],
    period: 6.5,
    delay: 1.2,
  },

  // "A quiet day": a cat lounging with nothing planned. Tail hanging back
  // (tail 3) at rest; now and then it swishes forward (tail 1) and back.
  'empty-schedule': {
    src: restingOrangeCat.body,
    layers: [restingOrangeCat.tail3, restingOrangeCat.tail1],
    ...petAssetSizes.restingOrangeCat,
    animations: ['gesture', 'fade'],
    period: BEAT,
    delay: TURN.restingOrangeCat,
  },

  // "All caught up" (empty-tasks) stays text-only: the side-peeking cat is already next to it.

  /* ---- Health Records: the gray cat's home ---- */

  // Alone on its page: hops up onto the owner-key card a moment after it loads.
  'records-peek': {
    src: grayPeekCat.open,
    frames: [grayPeekCat.wink],
    ...petAssetSizes.grayPeekCat,
    edge: 101.574,
    animations: ['hop'],
    period: 11,
    delay: 2.5,
  },
};

export const DEFAULT_VARIANT: Record<ArtSlot, ArtVariant> = {
  'greeting-motif': 'decoration',
  'pets-peek': 'peek-top',
  'add-pet-motif': 'inline',
  'schedule-corner': 'decoration',
  'tasks-peek': 'peek-side',
  'records-peek': 'peek-top',
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
