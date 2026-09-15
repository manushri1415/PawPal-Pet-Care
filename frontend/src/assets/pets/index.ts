/**
 * Pet illustration assets, normalised from the Canva exports.
 *
 * Every file inside one family shares the same viewBox (canvas size, scale
 * and pet position), so files can be stacked with `position: absolute` and
 * swapped by opacity with no shift. Families with a permanent `body` keep it
 * as its own file; the other files of that family hold only the parts that
 * change (Z's, tail). Imports resolve to URLs (Vite), for use as
 * `<img src={...} alt="" />`.
 *
 * Families are independent: each has its own canvas, and the presets below
 * carry each family's own animation values. Don't size one family against
 * another.
 */
import type { PeekFrameGeometry } from "../../components/PeekingPet";
import type { PetOverlayLoopProps } from "../../components/PetOverlayLoop";
import type { SidePeekGeometry } from "../../components/SidePeekingPet";
import catOrangePeekOpen from "./cats/cat-orange-peek-open.svg";
import catOrangePeekWink from "./cats/cat-orange-peek-wink.svg";
import catGrayPeekOpen from "./cats/cat-gray-peek-open.svg";
import catGrayPeekWink from "./cats/cat-gray-peek-wink.svg";
import catGraySidePeek1 from "./cats/cat-gray-side-peek-1.svg";
import catGraySidePeek2 from "./cats/cat-gray-side-peek-2.svg";
import catOrangeRestBase from "./cats/cat-orange-rest-base.svg";
import catOrangeRestTail1 from "./cats/cat-orange-rest-tail-1.svg";
import catOrangeRestTail2 from "./cats/cat-orange-rest-tail-2.svg";
import catOrangeRestTail3 from "./cats/cat-orange-rest-tail-3.svg";
import dogSleepBase from "./dogs/dog-sleep-base.svg";
import dogSleepZ1 from "./dogs/dog-sleep-z1.svg";
import dogSleepZ2 from "./dogs/dog-sleep-z2.svg";
import dogSleepZ3 from "./dogs/dog-sleep-z3.svg";

export const petAssets = {
  /** Cat peeking over a ledge (no ledge drawn in); the wink frame only changes the right eye. */
  orangePeekCat: { open: catOrangePeekOpen, wink: catOrangePeekWink },
  grayPeekCat: { open: catGrayPeekOpen, wink: catGrayPeekWink },
  /** Two poses holding a vertical edge; the edge line is at the same x in both. Mirror with CSS for the other side. */
  graySidePeekCat: { pose1: catGraySidePeek1, pose2: catGraySidePeek2 },
  /** Dog body, plus Z-only layers: z1 = Z, z2 = ZZ, z3 = ZZZ (each contains the one before). */
  sleepingDog: { body: dogSleepBase, z1: dogSleepZ1, z2: dogSleepZ2, z3: dogSleepZ3 },
  /** Cat body without a tail, plus tail-only layers: wrapped forward, arched, hanging back. */
  restingOrangeCat: {
    body: catOrangeRestBase,
    tail1: catOrangeRestTail1,
    tail2: catOrangeRestTail2,
    tail3: catOrangeRestTail3,
  },
} as const;

export type PetAssetFamily = keyof typeof petAssets;

/**
 * Shared canvas (viewBox) size of each family in SVG user units. Only the
 * ratio matters — use it for `width`/`height` or `aspect-ratio`.
 */
export const petAssetSizes: Record<PetAssetFamily, { width: number; height: number }> = {
  orangePeekCat: { width: 185.12, height: 108.03 },
  grayPeekCat: { width: 199.55, height: 111.63 },
  graySidePeekCat: { width: 141.93, height: 262.99 },
  sleepingDog: { width: 137.24, height: 87.23 },
  restingOrangeCat: { width: 234.08, height: 109.65 },
};

/**
 * Ready-made props for `<PeekingPet>`: the frame pair, where the body ends
 * (measured from the frames, viewBox units), and first-hop delays staggered
 * so the two cats never pop up at the same moment.
 *
 *   <PeekingPet {...peekingCats.orange} width={128} />
 */
export const peekingCats = {
  orange: {
    openFrame: catOrangePeekOpen,
    winkFrame: catOrangePeekWink,
    geometry: { width: 185.12, height: 108.03, bodyBottom: 98.396 },
    delay: 1.5,
  },
  gray: {
    openFrame: catGrayPeekOpen,
    winkFrame: catGrayPeekWink,
    geometry: { width: 199.55, height: 111.63, bodyBottom: 101.574 },
    delay: 4.3,
  },
} satisfies Record<string, { openFrame: string; winkFrame: string; geometry: PeekFrameGeometry; delay: number }>;

/**
 * Ready-made props for `<SidePeekingPet>`: pose 1 rests, pose 2 grabs the
 * edge; where the parent's edge crosses the frames (just past the wall line
 * drawn into them, which stays hidden) and the paw that reaches over it.
 *
 *   <SidePeekingPet {...sidePeekingCat} width={120} />
 */
export const sidePeekingCat = {
  restFrame: catGraySidePeek1,
  actionFrame: catGraySidePeek2,
  geometry: {
    width: 141.93,
    height: 262.99,
    edge: 18.257,
    reach: [
      [0, 0],
      [11.57, 0],
      [11.57, 127.746],
      [19.057, 128.872],
      [19.057, 162.759],
      [11.57, 157.987],
      [11.57, 262.99],
      [0, 262.99],
    ],
  },
  delay: 2,
} satisfies { restFrame: string; actionFrame: string; geometry: SidePeekGeometry; delay: number };

/**
 * Ready-made props for `<PetOverlayLoop>`, each with its own calm timing.
 *
 *   <PetOverlayLoop {...overlayLoops.sleepingDog} width={220} />
 */
export const overlayLoops = {
  /**
   * No Z's → Z → ZZ → ZZZ one by one, a pause, then all fade out and it
   * starts again; slow fades. Reduced motion shows ZZZ.
   */
  sleepingDog: {
    base: dogSleepBase,
    layers: [dogSleepZ1, dogSleepZ2, dogSleepZ3],
    size: petAssetSizes.sleepingDog,
    timing: {
      steps: [
        { layer: null, hold: 1.4 },
        { layer: 0, hold: 1.2 },
        { layer: 1, hold: 1.2 },
        { layer: 2, hold: 2.6 },
      ],
      fade: 0.45,
      blend: "cumulative",
      delay: 1.2,
    },
    stillLayer: 2,
  },
  /** Long rest on tail 1, then a quick 1 → 2 → 3 → 2 → 1 flick; reduced motion keeps tail 1. */
  restingOrangeCat: {
    base: catOrangeRestBase,
    layers: [catOrangeRestTail1, catOrangeRestTail2, catOrangeRestTail3],
    size: petAssetSizes.restingOrangeCat,
    timing: {
      steps: [
        { layer: 0, hold: 7 },
        { layer: 1, hold: 0.14 },
        { layer: 2, hold: 0.45 },
        { layer: 1, hold: 0.14 },
      ],
      fade: 0.18,
      blend: "crossfade",
      delay: 2.5,
    },
    stillLayer: 0,
  },
} satisfies Record<string, Pick<PetOverlayLoopProps, "base" | "layers" | "size" | "timing" | "stillLayer">>;
