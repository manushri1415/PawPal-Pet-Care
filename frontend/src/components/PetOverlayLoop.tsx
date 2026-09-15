import type { CSSProperties } from "react";
import "./PetOverlayLoop.css";

/** One state of the loop: which overlay is showing and for how long. */
export interface OverlayStep {
  /** Index into `layers`, or `null` for no overlay. */
  layer: number | null;
  /** Seconds the state is held, not counting the fade into the next state. */
  hold: number;
}

export interface OverlayLoopTiming {
  /** States in order. After the last one the loop fades back to the first. */
  steps: OverlayStep[];
  /** Seconds each change between states takes. 0 = hard cut. */
  fade: number;
  /**
   * `crossfade`: the outgoing overlay fades out while the next fades in
   * (separate drawings, e.g. tail positions).
   * `cumulative`: every layer contains the one before it (Z → ZZ → ZZZ), so
   * only the part being added or removed fades; the shared part stays solid.
   */
  blend: "crossfade" | "cumulative";
  /** Seconds until the first change. Default 0. */
  delay?: number;
}

/** Numbers are pixels; strings are any CSS length. */
type CssLength = number | string;

export interface PetOverlayLoopProps {
  /** Always visible and never animated: no opacity, no transform. */
  base: string;
  /** Overlays drawn on the same canvas (viewBox) as `base`. */
  layers: string[];
  /** The family's shared viewBox size; sets the aspect ratio before the images load. */
  size: { width: number; height: number };
  timing: OverlayLoopTiming;
  /** Overlay shown when not animated (reduced motion, `animated={false}`). `null` hides them. Default: the first step's. */
  stillLayer?: number | null;
  /** Whether overlays are drawn above (default) or below the base. */
  overlay?: "above" | "below";
  /** Rendered width. Default 160px. */
  width?: CssLength;
  /** Left / top on the positioned parent. Giving either positions the illustration absolutely. */
  x?: CssLength;
  y?: CssLength;
  /** `false` holds the still state. */
  animated?: boolean;
  className?: string;
  style?: CSSProperties;
}

const len = (value: CssLength) => (typeof value === "number" ? `${value}px` : value);

/** Tiny stable hash, so identical timings share one set of keyframes. */
function hash(text: string) {
  let h = 5381;
  for (let i = 0; i < text.length; i++) h = ((h << 5) + h + text.charCodeAt(i)) | 0;
  return (h >>> 0).toString(36);
}

interface Point {
  /** Seconds into the cycle. */
  t: number;
  opacity: number;
  /** The segment starting here is a fade (eased) rather than a hold or a cut. */
  fade?: boolean;
}

/** An instant change is two keyframes this far apart (seconds). */
const CUT = 0.0005;

/**
 * Opacity points per layer over one cycle. Points only move forward in time
 * and never share an offset (CSS merges keyframes with equal offsets, which
 * would turn a hold into a slow ramp); the cycle ends exactly on the first
 * state again.
 */
function layerPoints(timing: OverlayLoopTiming, count: number): { cycle: number; points: Point[][] } {
  const { steps, fade, blend } = timing;
  const points: Point[][] = Array.from({ length: count }, () => []);
  let t = 0;
  steps.forEach((step, k) => {
    const next = steps[(k + 1) % steps.length];
    const holdEnd = t + step.hold;
    const fadeEnd = holdEnd + fade;
    for (let j = 0; j < count; j++) {
      const p = points[j];
      const now = step.layer === j ? 1 : 0;
      const then = next.layer === j ? 1 : 0;
      if (p.length === 0) p.push({ t, opacity: now });
      if (now === then) {
        p.push({ t: fadeEnd, opacity: now });
      } else if (fade === 0) {
        p.push({ t: holdEnd - CUT, opacity: now }, { t: holdEnd, opacity: then });
      } else {
        // Cumulative: the higher layer covers the lower one exactly. Growing,
        // the new layer fades in over the old one, which drops out once it is
        // covered. Shrinking, the lower layer is back underneath before the
        // top one starts to fade.
        const growing = (next.layer ?? -1) > (step.layer ?? -1);
        const fadesItself = blend === "crossfade" || (growing ? then === 1 : now === 1);
        if (fadesItself) {
          p.push({ t: holdEnd, opacity: now, fade: true }, { t: fadeEnd, opacity: then });
        } else if (growing) {
          p.push({ t: fadeEnd - CUT, opacity: now }, { t: fadeEnd, opacity: then });
        } else {
          p.push({ t: holdEnd, opacity: now }, { t: holdEnd + CUT, opacity: then }, { t: fadeEnd, opacity: then });
        }
      }
    }
    t = fadeEnd;
  });
  return { cycle: t, points };
}

/**
 * Fade easing. A crossfade swaps two different drawings, so it crosses over
 * steeply: each stays close to solid until the swap and the moment where both
 * are half transparent is very short. A cumulative fade adds or removes one
 * part over what stays, so it can ease gently.
 */
const FADE_EASING: Record<OverlayLoopTiming["blend"], string> = {
  crossfade: "cubic-bezier(0.75,0,0.25,1)",
  cumulative: "ease-in-out",
};

function keyframesCss(name: string, points: Point[], cycle: number, blend: OverlayLoopTiming["blend"]) {
  const pct = (t: number) => `${Math.min(100, Math.max(0, (t / cycle) * 100)).toFixed(4)}%`;
  const frames = points.map(
    (p) => `${pct(p.t)}{opacity:${p.opacity};animation-timing-function:${p.fade ? FADE_EASING[blend] : "linear"}}`,
  );
  return `@keyframes ${name}{${frames.join("")}}`;
}

/**
 * A static pet with overlay drawings that take turns on a loop — Z's above a
 * sleeping dog, tail positions on a resting cat.
 *
 * The base image never animates. Each overlay is an absolutely positioned
 * image on the same canvas, animated with CSS opacity keyframes generated
 * from `timing` (so hold lengths and fade length are independent). The
 * keyframes are shared per timing through a hoisted `<style>`; no JS runs
 * after render.
 *
 * Decorative (`aria-hidden`, `pointer-events: none`). Reduced motion or
 * `animated={false}` shows `stillLayer` and nothing moves.
 */
export function PetOverlayLoop({
  base,
  layers,
  size,
  timing,
  stillLayer,
  overlay = "above",
  width,
  x,
  y,
  animated = true,
  className,
  style,
}: PetOverlayLoopProps) {
  const { cycle, points } = layerPoints(timing, layers.length);
  const id = `pet-loop-${hash(JSON.stringify([timing.steps, timing.fade, timing.blend, layers.length]))}`;
  const css = points.map((p, j) => keyframesCss(`${id}-${j}`, p, cycle, timing.blend)).join("\n");
  const firstChange = timing.steps[0]?.hold ?? 0;
  const still = stillLayer === undefined ? (timing.steps[0]?.layer ?? null) : stillLayer;
  const placed = x !== undefined || y !== undefined;

  const vars: Record<string, string | number> = {
    "--pet-loop-ratio": `${size.width} / ${size.height}`,
    "--pet-loop-cycle": `${cycle}s`,
    // The loop starts on the first step's hold; shift it so the first change lands at `delay`.
    "--pet-loop-start": `${(timing.delay ?? 0) - firstChange}s`,
  };
  if (width !== undefined) vars["--pet-loop-width"] = len(width);
  if (x !== undefined) vars["--pet-loop-x"] = len(x);
  if (y !== undefined) vars["--pet-loop-y"] = len(y);

  const classes = [
    "pet-loop",
    `pet-loop--${overlay}`,
    placed && "pet-loop--placed",
    !animated && "pet-loop--still",
    className,
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <div className={classes} style={{ ...vars, ...style } as CSSProperties} aria-hidden="true">
      <style href={id} precedence="pet-loop">
        {css}
      </style>
      <img className="pet-loop__base" src={base} alt="" draggable={false} />
      <div className="pet-loop__effects">
        {layers.map((src, j) => (
          <img
            key={j}
            className={`pet-loop__layer${j === still ? " pet-loop__layer--still" : ""}`}
            style={{ "--pet-loop-anim": `${id}-${j}` } as CSSProperties}
            src={src}
            alt=""
            draggable={false}
          />
        ))}
      </div>
    </div>
  );
}
