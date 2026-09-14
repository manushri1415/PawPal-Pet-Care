import type { CSSProperties } from "react";
import "./SidePeekingPet.css";

/**
 * Where things are inside a side-peek frame pair, in the family's viewBox
 * units. The frames are drawn peeking out to the right from behind a vertical
 * edge. Presets live in `assets/pets` (`sidePeekingCat`).
 */
export interface SidePeekGeometry {
  /** Shared viewBox width / height of the two frames. */
  width: number;
  height: number;
  /**
   * x where the parent's edge crosses the artwork. Everything left of it is
   * behind the parent. It sits just right of the wall line drawn into the
   * frames, so that line never shows.
   */
  edge: number;
  /**
   * Polygon of the action frame's part left of `edge` that is drawn in front
   * of the parent: the paw and arm reaching over the edge, without the drawn
   * wall line.
   */
  reach: [number, number][];
}

/** Numbers are pixels; strings are any CSS length. */
type CssLength = number | string;

export interface SidePeekingPetProps {
  /** Resting pose. Shown whenever the pet is out, except during the action. */
  restFrame: string;
  /** Action pose (same canvas), shown once per cycle while the pet is settled. */
  actionFrame: string;
  geometry: SidePeekGeometry;
  /** Which edge of the positioned parent the pet peeks around. Default `right`. */
  side?: "right" | "left";
  /** Pet width (absolute length). Default 120px. */
  width?: CssLength;
  /**
   * How far the edge is outside the parent's padding box. Default 0: the
   * pet's cut side covers a border on that side, so no light border line
   * shows between parent and pet.
   */
  x?: CssLength;
  /** Top of the pet, relative to the parent's top edge. Default 16px. */
  y?: CssLength;
  /**
   * How far the slide overshoots the resting position. Default 0: the pet's
   * side is cut flat at the edge, so any overshoot briefly opens a gap there.
   */
  hopHeight?: CssLength;
  /** Seconds until the pet first starts coming out. Later peeks follow every `duration`. Default 2. */
  delay?: number;
  /** Seconds per peek → action → hide cycle. Default 12. */
  duration?: number;
  /** `false` shows the pet calmly out in its resting pose (same as reduced motion). */
  animated?: boolean;
  className?: string;
  style?: CSSProperties;
}

const len = (value: CssLength) => (typeof value === "number" ? `${value}px` : value);
const pct = (value: number, of: number) => `${Math.round((value / of) * 1e6) / 1e4}%`;

/**
 * A pet that now and then slides out sideways from behind the edge of its
 * parent, does its action pose, and slides back.
 *
 * Structure: the pet sits in a viewport on the open side of the edge
 * (`overflow: hidden`), so while it is pulled back nothing of it shows, and
 * the wall line drawn into the frames — left of `geometry.edge` — never does.
 * A second viewport on the parent's side shows only the action frame's reach
 * (the paw over the edge), clipped to `geometry.reach`. The slide is a
 * `transform: translateX` keyframe animation; the pose swap is opacity
 * keyframes with the same duration and delay, and only happens while the pet
 * is settled. `side="left"` mirrors the whole thing.
 *
 * Decorative (`aria-hidden`, `pointer-events: none`) and absolutely
 * positioned. The parent needs `position: relative` and must not clip
 * overflow; leave free space beside the edge where the pet appears.
 */
export function SidePeekingPet({
  restFrame,
  actionFrame,
  geometry: g,
  side = "right",
  width,
  x,
  y,
  hopHeight,
  delay,
  duration,
  animated = true,
  className,
  style,
}: SidePeekingPetProps) {
  const vars: Record<string, string | number> = {
    "--side-peek-ratio": g.width / g.height,
    "--side-peek-edge": g.edge / g.width,
  };
  if (width !== undefined) vars["--side-peek-width"] = len(width);
  if (x !== undefined) vars["--side-peek-x"] = len(x);
  if (y !== undefined) vars["--side-peek-y"] = len(y);
  if (hopHeight !== undefined) vars["--side-peek-hop"] = len(hopHeight);
  if (delay !== undefined) vars["--side-peek-delay"] = `${delay}s`;
  if (duration !== undefined) vars["--side-peek-duration"] = `${duration}s`;

  const reach = `polygon(${g.reach.map(([px, py]) => `${pct(px, g.width)} ${pct(py, g.height)}`).join(", ")})`;
  const classes = ["side-peek", `side-peek--${side}`, !animated && "side-peek--still", className]
    .filter(Boolean)
    .join(" ");

  return (
    <div className={classes} style={{ ...vars, ...style } as CSSProperties} aria-hidden="true">
      <div className="side-peek__viewport">
        <div className="side-peek__pet">
          <img className="side-peek__frame side-peek__frame--rest" src={restFrame} alt="" draggable={false} />
          <img className="side-peek__frame side-peek__frame--action" src={actionFrame} alt="" draggable={false} />
        </div>
      </div>
      <div className="side-peek__reach">
        <div className="side-peek__pet">
          <img
            className="side-peek__frame side-peek__frame--action"
            style={{ clipPath: reach }}
            src={actionFrame}
            alt=""
            draggable={false}
          />
        </div>
      </div>
    </div>
  );
}
