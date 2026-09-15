import type { CSSProperties } from "react";
import "./PeekingPet.css";

/**
 * Where things are inside a peek frame pair, in the family's viewBox units.
 * Presets for the cat families live in `assets/pets` (`peekingCats`).
 */
export interface PeekFrameGeometry {
  /** Shared viewBox width / height of the open and wink frames. */
  width: number;
  height: number;
  /**
   * Lowest point of the body's bottom edge; the drawing is cut flat there.
   * At rest this line sits on the edge the pet peeks over. Only the paws
   * reach further down.
   */
  bodyBottom: number;
}

/** Numbers are pixels; strings are any CSS length (`"8rem"`, `"calc(100% - 160px)"`). */
type CssLength = number | string;

export interface PeekingPetProps {
  /** Open-eyes frame. Shown whenever the pet is up. */
  openFrame: string;
  /** Wink frame, same canvas as `openFrame`; layered on top once per cycle. */
  winkFrame: string;
  geometry: PeekFrameGeometry;
  /** Placement. `top`: the pet peeks over the top edge of the positioned parent. */
  variant?: "top";
  /**
   * `over` (default): the paws hang over the edge in front of the parent, as drawn.
   * `behind`: the pet stays entirely behind the edge; the paws are cut off by it.
   */
  paws?: "over" | "behind";
  /** Pet width (absolute length). Default 128px. */
  width?: CssLength;
  /** Left edge of the pet, relative to the parent. Default 24px. */
  x?: CssLength;
  /**
   * Where the edge is, relative to the parent's padding box. Default 0. For a
   * parent with a top border pass minus its width (e.g. `-1`), so the pet sits
   * on the outer edge and the border stays in front of it.
   */
  y?: CssLength;
  /**
   * How far the hop overshoots the resting position. Default 7px. With
   * `paws="over"` it is never less than what the paws need to clear the edge.
   */
  hopHeight?: CssLength;
  /** Seconds until the first hop starts. Later hops follow every `duration`. Default 1.5. */
  delay?: number;
  /** Seconds per hop → wink → drop cycle. Default 10. */
  duration?: number;
  /** `false` shows the pet calmly resting on the edge with open eyes (same as reduced motion). */
  animated?: boolean;
  className?: string;
  style?: CSSProperties;
}

const len = (value: CssLength) => (typeof value === "number" ? `${value}px` : value);

/**
 * A pet that now and then hops up from behind an edge (the top of a card),
 * winks, and drops back.
 *
 * Structure: nothing is drawn for the edge itself. The pet sits in a viewport
 * whose bottom is the edge (`overflow: hidden`), so while it is lowered
 * nothing of it shows. With `paws="over"` a second, shallow viewport just
 * below the edge draws the hanging paws in front of the parent; it is only
 * shown from the top of the hop to the lift-off, when the paws are clear above
 * the edge. The hop is a `transform: translateY` keyframe animation; the wink
 * and the paws layer are keyframes with the same duration and delay, so they
 * stay in step with it.
 *
 * Decorative (`aria-hidden`, `pointer-events: none`) and absolutely
 * positioned, so it never takes layout space or blocks clicks. The parent
 * needs `position: relative` (or the `peek-pet-host` class), must not clip
 * overflow, and should have free space above where the pet appears.
 */
export function PeekingPet({
  openFrame,
  winkFrame,
  geometry: g,
  variant = "top",
  paws = "over",
  width,
  x,
  y,
  hopHeight,
  delay,
  duration,
  animated = true,
  className,
  style,
}: PeekingPetProps) {
  const vars: Record<string, string | number> = {
    "--peek-pet-ratio": g.width / g.height,
    "--peek-pet-rest": g.bodyBottom / g.height,
  };
  if (width !== undefined) vars["--peek-pet-width"] = len(width);
  if (x !== undefined) vars["--peek-pet-x"] = len(x);
  if (y !== undefined) vars["--peek-pet-y"] = len(y);
  if (hopHeight !== undefined) vars["--peek-pet-hop"] = len(hopHeight);
  if (delay !== undefined) vars["--peek-pet-delay"] = `${delay}s`;
  if (duration !== undefined) vars["--peek-pet-duration"] = `${duration}s`;

  const classes = [
    "peek-pet",
    `peek-pet--${variant}`,
    `peek-pet--paws-${paws}`,
    !animated && "peek-pet--still",
    className,
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <div className={classes} style={{ ...vars, ...style } as CSSProperties} aria-hidden="true">
      <div className="peek-pet__viewport">
        <div className="peek-pet__pet">
          <img className="peek-pet__frame" src={openFrame} alt="" draggable={false} />
          <img className="peek-pet__frame peek-pet__frame--wink" src={winkFrame} alt="" draggable={false} />
        </div>
      </div>
      {paws === "over" && (
        <div className="peek-pet__paws">
          <div className="peek-pet__pet">
            <img className="peek-pet__frame" src={openFrame} alt="" draggable={false} />
          </div>
        </div>
      )}
    </div>
  );
}
