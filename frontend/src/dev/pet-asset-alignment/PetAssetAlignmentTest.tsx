import { useEffect, useState } from "react";
import { petAssets, petAssetSizes } from "../../assets/pets";
import { OverlayLoopsDemo } from "./OverlayLoopsDemo";
import { PeekingPetsDemo } from "./PeekingPetsDemo";
import { SidePeekDemo } from "./SidePeekDemo";

/**
 * TEMPORARY development-only page: the animation demos, then a check that
 * every file of each pet illustration family stacks exactly — no jumping, no
 * scale change, no canvas shift, no background box, no clipping. Not used by
 * the app.
 *
 * Views per family (families with a permanent body draw it under every frame):
 *  - Stacked: all frames absolutely positioned, swapped by opacity.
 *  - Onion skin: all frames visible at once; any misalignment shows as
 *    doubled outlines.
 *  - Difference: each frame against the first (black = pixel-identical).
 *  - Files: each file alone, so its own canvas edge can be compared.
 */

type FamilyKey = keyof typeof petAssets;
type Backdrop = "checker" | "cream" | "dark";

interface Frame {
  name: string;
  src: string;
}

interface FamilyView {
  label: string;
  /** Permanent body drawn under every frame. */
  base?: Frame;
  frames: Frame[];
}

const FAMILY_VIEWS: Record<FamilyKey, FamilyView> = {
  orangePeekCat: {
    label: "Peeking orange/white cat",
    frames: [
      { name: "open", src: petAssets.orangePeekCat.open },
      { name: "wink", src: petAssets.orangePeekCat.wink },
    ],
  },
  grayPeekCat: {
    label: "Peeking gray cat",
    frames: [
      { name: "open", src: petAssets.grayPeekCat.open },
      { name: "wink", src: petAssets.grayPeekCat.wink },
    ],
  },
  graySidePeekCat: {
    label: "Side-peeking gray cat (unchanged)",
    frames: [
      { name: "pose1", src: petAssets.graySidePeekCat.pose1 },
      { name: "pose2", src: petAssets.graySidePeekCat.pose2 },
    ],
  },
  sleepingDog: {
    label: "Sleeping dog · body + Z layers",
    base: { name: "body", src: petAssets.sleepingDog.body },
    frames: [
      { name: "z1", src: petAssets.sleepingDog.z1 },
      { name: "z2", src: petAssets.sleepingDog.z2 },
      { name: "z3", src: petAssets.sleepingDog.z3 },
    ],
  },
  restingOrangeCat: {
    label: "Resting orange cat · body + tail layers",
    base: { name: "body", src: petAssets.restingOrangeCat.body },
    frames: [
      { name: "tail1", src: petAssets.restingOrangeCat.tail1 },
      { name: "tail2", src: petAssets.restingOrangeCat.tail2 },
      { name: "tail3", src: petAssets.restingOrangeCat.tail3 },
    ],
  },
};

const FAMILIES = Object.keys(FAMILY_VIEWS) as FamilyKey[];

export function PetAssetAlignmentTest() {
  const [width, setWidth] = useState(320);
  const [backdrop, setBackdrop] = useState<Backdrop>("checker");
  const [playing, setPlaying] = useState(true);
  const [intervalMs, setIntervalMs] = useState(450);
  const [tick, setTick] = useState(0);
  const [showEdge, setShowEdge] = useState(true);
  const [mirror, setMirror] = useState(false);

  useEffect(() => {
    if (!playing) return;
    const id = window.setInterval(() => setTick((t) => t + 1), intervalMs);
    return () => window.clearInterval(id);
  }, [playing, intervalMs]);

  return (
    <main className="aln">
      <p className="aln-banner">
        Temporary development page — pet asset and animation check. Not part of the production app.
      </p>
      <h1>Pet illustrations</h1>

      <PeekingPetsDemo />
      <SidePeekDemo />
      <OverlayLoopsDemo />

      <h2 className="aln-section">Frame alignment</h2>
      <div className="aln-controls">
        <label>
          Width{" "}
          <input
            type="range"
            min={60}
            max={1200}
            step={10}
            value={width}
            onChange={(e) => setWidth(Number(e.target.value))}
          />{" "}
          {width}px
        </label>
        <label>
          Backdrop{" "}
          <select value={backdrop} onChange={(e) => setBackdrop(e.target.value as Backdrop)}>
            <option value="checker">Checkerboard</option>
            <option value="cream">Cream</option>
            <option value="dark">Dark</option>
          </select>
        </label>
        <label>
          <input type="checkbox" checked={playing} onChange={(e) => setPlaying(e.target.checked)} /> Flip
          frames every{" "}
          <input
            type="number"
            min={100}
            max={3000}
            step={50}
            value={intervalMs}
            onChange={(e) => setIntervalMs(Math.max(100, Number(e.target.value) || 100))}
          />{" "}
          ms
        </label>
        <button type="button" onClick={() => setTick((t) => t + 1)}>
          Next frame
        </button>
        <label>
          <input type="checkbox" checked={showEdge} onChange={(e) => setShowEdge(e.target.checked)} /> Show
          canvas edge
        </label>
        <label>
          <input type="checkbox" checked={mirror} onChange={(e) => setMirror(e.target.checked)} /> Mirror
          (right-edge use)
        </label>
      </div>

      {FAMILIES.map((key) => (
        <FamilySection
          key={key}
          familyKey={key}
          width={width}
          backdrop={backdrop}
          tick={tick}
          showEdge={showEdge}
          mirror={mirror}
        />
      ))}
    </main>
  );
}

interface FamilySectionProps {
  familyKey: FamilyKey;
  width: number;
  backdrop: Backdrop;
  tick: number;
  showEdge: boolean;
  mirror: boolean;
}

function FamilySection({ familyKey, width, backdrop, tick, showEdge, mirror }: FamilySectionProps) {
  const { label, base, frames } = FAMILY_VIEWS[familyKey];
  const size = petAssetSizes[familyKey];
  const active = tick % frames.length;
  const first = frames[0];
  const boxClass = ["aln-box", `aln-bg-${backdrop}`, showEdge && "aln-edge", mirror && "aln-mirror"]
    .filter(Boolean)
    .join(" ");
  const withBase = (frame: Frame) => (base ? [base, frame] : [frame]);

  return (
    <section className="aln-family">
      <h3 className="aln-family-title">{label}</h3>
      <p className="aln-meta">
        viewBox 0 0 {size.width} {size.height} · {base ? `body + ` : ""}frames: {frames.map((f) => f.name).join(", ")}
      </p>

      <div className="aln-row">
        <figure>
          <div className={`${boxClass} aln-stack`} style={{ width }}>
            {base && <img src={base.src} alt="" />}
            {frames.map((f, i) => (
              <img key={f.name} src={f.src} alt="" style={{ opacity: i === active ? 1 : 0 }} />
            ))}
          </div>
          <figcaption>
            Stacked, flipping · now <b>{frames[active].name}</b>
            {base && " (body always on)"}
          </figcaption>
        </figure>

        <figure>
          <div className={`${boxClass} aln-stack aln-onion`} style={{ width }}>
            {base && <img src={base.src} alt="" />}
            {frames.map((f) => (
              <img key={f.name} src={f.src} alt="" />
            ))}
          </div>
          <figcaption>Onion skin · all frames at once</figcaption>
        </figure>

        {frames.slice(1).map((f) => (
          <figure key={f.name}>
            <div className={`aln-box aln-diff${showEdge ? " aln-edge" : ""}`} style={{ width }}>
              {[first, f].map((frame) => (
                <div className="aln-layer" key={frame.name}>
                  {withBase(frame).map((layer) => (
                    <img key={layer.name} src={layer.src} alt="" />
                  ))}
                </div>
              ))}
            </div>
            <figcaption>
              Difference {base ? "body+" : ""}
              {first.name} ↔ {base ? "body+" : ""}
              {f.name} · black = identical
            </figcaption>
          </figure>
        ))}
      </div>

      <div className="aln-row">
        {[...(base ? [base] : []), ...frames].map((f) => (
          <figure key={f.name}>
            <div className={boxClass} style={{ width }}>
              <img src={f.src} alt="" />
            </div>
            <figcaption>{f.name} (file alone)</figcaption>
          </figure>
        ))}
      </div>
    </section>
  );
}
