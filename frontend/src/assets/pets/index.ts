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
import dogAwakeBase from "./dogs/dog-awake-base.svg";
import dogAwakeTail1 from "./dogs/dog-awake-tail-1.svg";
import dogAwakeTail2 from "./dogs/dog-awake-tail-2.svg";
import dogAwakeTail3 from "./dogs/dog-awake-tail-3.svg";
import officialLogo from "./misc/official-pawpal-logo.svg";
import customCursor24 from "./misc/custom-cursor-24.png";
import customCursor48 from "./misc/custom-cursor-48.png";
import customHandCursor24 from "./misc/custom-hand-cursor-24.png";
import customHandCursor48 from "./misc/custom-hand-cursor-48.png";
import typingCursor24 from "./misc/typing-cursor-24.png";
import typingCursor48 from "./misc/typing-cursor-48.png";

export const petAssets = {
  /** Cat peeking over a ledge (no ledge drawn in); the wink frame only changes the right eye. */
  orangePeekCat: { open: catOrangePeekOpen, wink: catOrangePeekWink },
  grayPeekCat: { open: catGrayPeekOpen, wink: catGrayPeekWink },
  /** Two poses holding a vertical edge; the edge line is at the same x in both. Mirror with CSS for the other side. */
  graySidePeekCat: { pose1: catGraySidePeek1, pose2: catGraySidePeek2 },
  /** Dog body, plus Z-only layers: z1 = Z, z2 = ZZ, z3 = ZZZ (each contains the one before). */
  sleepingDog: { body: dogSleepBase, z1: dogSleepZ1, z2: dogSleepZ2, z3: dogSleepZ3 },
  /**
   * The dog awake and grinning, lying down — the landing hero's shopkeeper
   * under its "Open" sign, and only there (the sleeping dog stays the one for
   * empty, quiet and loading states). Body without a tail, plus tail-only
   * layers, high to low: tail1 raised forward over the back, tail2 up behind
   * (the natural pose), tail3 hanging down. Split from the Canva board
   * misc/dog-tail-wiggle-animation.svg, which is kept as the master and not
   * imported (misc/dog-open-eyes.svg, the earlier single drawing, likewise).
   */
  awakeDog: { body: dogAwakeBase, tail1: dogAwakeTail1, tail2: dogAwakeTail2, tail3: dogAwakeTail3 },
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
  awakeDog: { width: 418.879, height: 266.226 },
};

/**
 * The brand mark: the official PawPal+ logo — two paws, symbol only, so the
 * "PawPal+" wordmark is set in text beside it (components/BrandBadge). A
 * Canva export (a raster with a luminance mask inside an SVG wrapper): it
 * scales with the page but is not recolourable.
 */
export const brandAssets = {
  logo: officialLogo,
  /** viewBox size — for `aspect-ratio`, so the mark has its width before it loads. */
  logoSize: { width: 857.25, height: 973.5 },
} as const;

/**
 * PawPal's cursors: the pixel arrow (page-wide default), the pixel hand
 * (anything clickable) and the I-beam (text fields). Browsers cap cursor
 * images at 128×128 and the source SVGs (misc/custom-cursor.svg 1062×1096,
 * misc/custom-hand-cursor.svg 1306×1478, misc/typing-cursor.svg 563×1906 —
 * kept as masters and deliberately not imported, so they never ship) are far
 * larger, so they cannot be cursors themselves. The PNGs are them rendered by
 * a headless browser on transparency, trimmed to the drawing, longest side
 * 24px (1x) and 48px (2x). styles/tokens.css references the 1x files
 * (`--pp-cursor-default`, `--pp-cursor-pointer`, `--pp-cursor-text`).
 * Hotspots are in 1x px: the arrow's tip, the index fingertip, the middle of
 * the beam.
 */
export const cursorAssets = {
  arrow: { x1: customCursor24, x2: customCursor48, hotspot: [1, 1] },
  hand: { x1: customHandCursor24, x2: customHandCursor48, hotspot: [3, 1] },
  text: { x1: typingCursor24, x2: typingCursor48, hotspot: [3, 12] },
} as const;

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
  /**
   * Long rest with the tail hanging back (tail 3), then a quick swish forward
   * (tail 1) and back — 3 → 1 → 3, the same flick as the dashboard's "quiet
   * day" cat. Tail 2 stays in the family for the dev page but is never shown
   * here. Reduced motion keeps tail 3.
   */
  restingOrangeCat: {
    base: catOrangeRestBase,
    layers: [catOrangeRestTail1, catOrangeRestTail2, catOrangeRestTail3],
    size: petAssetSizes.restingOrangeCat,
    timing: {
      steps: [
        { layer: 2, hold: 7 },
        { layer: 0, hold: 0.5 },
      ],
      fade: 0.18,
      blend: "crossfade",
      delay: 2.5,
    },
    stillLayer: 2,
  },
  /**
   * The awake dog's wag: a rest with the tail up behind (tail 2), then a
   * quick happy wag through the other two — 2 → 1 → 2 → 3 → 2 → 1 → 2 → 3 —
   * and back to rest. Short crossfades so it reads as motion, not a blink.
   * The tails are drawn BELOW the body, so each tail's base tucks behind the
   * rump outline instead of sitting on top of it. Reduced motion keeps tail 2.
   */
  awakeDog: {
    base: dogAwakeBase,
    layers: [dogAwakeTail1, dogAwakeTail2, dogAwakeTail3],
    overlay: "below",
    size: petAssetSizes.awakeDog,
    timing: {
      steps: [
        { layer: 1, hold: 3.2 },
        { layer: 0, hold: 0.14 },
        { layer: 1, hold: 0.08 },
        { layer: 2, hold: 0.14 },
        { layer: 1, hold: 0.08 },
        { layer: 0, hold: 0.14 },
        { layer: 1, hold: 0.08 },
        { layer: 2, hold: 0.14 },
      ],
      fade: 0.07,
      blend: "crossfade",
      delay: 1.6,
    },
    stillLayer: 1,
  },
} satisfies Record<string, Pick<PetOverlayLoopProps, "base" | "layers" | "size" | "timing" | "stillLayer"> & Partial<Pick<PetOverlayLoopProps, "overlay">>>;
