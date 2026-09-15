import { useEffect, useRef, useState } from "react";
import { PeekingPet } from "../../components/PeekingPet";
import { peekingCats } from "../../assets/pets";

/**
 * TEMPORARY development-only demo of <PeekingPet> for approving the hop
 * motion. The scrubber pauses the CSS animations through the Web Animations
 * API — a test-page convenience only; the component itself uses no JS timing.
 */

type Stage = "cream" | "white" | "dark";
type Paws = "over" | "behind";

const PHASES: [number, string][] = [
  [0.45, "hidden"],
  [0.495, "hop up"],
  [0.525, "dropping onto the edge"],
  [0.565, "small bounce"],
  [0.66, "resting"],
  [0.686, "wink"],
  [0.85, "resting"],
  [0.865, "lift-off"],
  [0.9, "dropping"],
  [1, "hidden"],
];

function phaseLabel(p: number) {
  return PHASES.find(([end]) => p < end)?.[1] ?? "hidden";
}

/** Height the pet reaches above the edge at rest, for spacing the demo cards. */
function restHeight(width: number) {
  return Math.max(
    ...Object.values(peekingCats).map((cat) => (width * cat.geometry.bodyBottom) / cat.geometry.width),
  );
}

export function PeekingPetsDemo() {
  const [width, setWidth] = useState(128);
  const [paws, setPaws] = useState<Paws>("over");
  const [hop, setHop] = useState(7);
  const [duration, setDuration] = useState(10);
  const [orangeDelay, setOrangeDelay] = useState(peekingCats.orange.delay);
  const [grayDelay, setGrayDelay] = useState(peekingCats.gray.delay);
  const [still, setStill] = useState(false);
  const [debug, setDebug] = useState(false);
  const [scrub, setScrub] = useState(false);
  const [phase, setPhase] = useState(0.75);
  const [stage, setStage] = useState<Stage>("cream");
  const [magnify, setMagnify] = useState(1);
  const [run, setRun] = useState(0);
  const stageRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const root = stageRef.current;
    if (!root || !scrub) return;
    for (const animation of root.getAnimations({ subtree: true })) {
      const timing = animation.effect?.getTiming();
      const cycle = Number(timing?.duration);
      if (!timing || !Number.isFinite(cycle)) continue;
      animation.pause();
      animation.currentTime = Number(timing.delay ?? 0) + (phase + 1) * cycle;
    }
  }, [scrub, phase, run, width, paws, hop, duration, orangeDelay, grayDelay, still, magnify]);

  // y = -1: the cards have a 1px border, so the edge the cats peek over is the border's outer edge.
  const common = { width, paws, y: -1, hopHeight: hop, duration, animated: !still };
  // The overshoot can be raised to what the paws need to clear the edge (about 5.4% of the width).
  const clearance = Math.ceil(restHeight(width) + Math.max(hop, width * 0.055) + 30);

  const toggleScrub = (on: boolean) => {
    setScrub(on);
    if (!on) setRun((r) => r + 1); // restart so both cats get their real stagger back
  };

  return (
    <section className="aln-family aln-peek" data-peek-demo>
      <h2>Peeking cats · hop</h2>
      <p className="aln-meta">
        No ledge is drawn: each cat hops up from behind the card's top edge, lands with its paws over the edge, winks
        once settled, then lifts off and drops back. Orange first hop at {orangeDelay}s, gray at {grayDelay}s, then
        every {duration}s.
      </p>

      <div className="aln-peek-controls">
        <label>
          Pet width{" "}
          <input type="range" min={64} max={320} value={width} onChange={(e) => setWidth(Number(e.target.value))} />{" "}
          {width}px
        </label>
        <label>
          Paws{" "}
          <select value={paws} onChange={(e) => setPaws(e.target.value as Paws)}>
            <option value="over">Over the edge (as drawn)</option>
            <option value="behind">Behind the edge</option>
          </select>
        </label>
        <label>
          Overshoot{" "}
          <input type="range" min={0} max={16} value={hop} onChange={(e) => setHop(Number(e.target.value))} /> {hop}px
          {paws === "over" && " (min: paws clear the edge)"}
        </label>
        <label>
          Cycle{" "}
          <input type="range" min={6} max={16} step={0.5} value={duration} onChange={(e) => setDuration(Number(e.target.value))} />{" "}
          {duration}s
        </label>
        <label>
          Orange delay{" "}
          <input type="number" min={0} max={30} step={0.1} value={orangeDelay} onChange={(e) => setOrangeDelay(Number(e.target.value) || 0)} />s
        </label>
        <label>
          Gray delay{" "}
          <input type="number" min={0} max={30} step={0.1} value={grayDelay} onChange={(e) => setGrayDelay(Number(e.target.value) || 0)} />s
        </label>
        <label>
          Stage{" "}
          <select value={stage} onChange={(e) => setStage(e.target.value as Stage)}>
            <option value="cream">Cream</option>
            <option value="white">White</option>
            <option value="dark">Dark</option>
          </select>
        </label>
        <label>
          Magnify{" "}
          <select value={magnify} onChange={(e) => setMagnify(Number(e.target.value))}>
            <option value={1}>1×</option>
            <option value={2}>2×</option>
            <option value={3}>3×</option>
          </select>
        </label>
        <label>
          <input type="checkbox" checked={still} onChange={(e) => setStill(e.target.checked)} /> Still (reduced-motion
          look)
        </label>
        <label>
          <input type="checkbox" checked={debug} onChange={(e) => setDebug(e.target.checked)} /> Show clip boxes
        </label>
        <button type="button" onClick={() => setRun((r) => r + 1)}>
          Replay from load
        </button>
      </div>

      <div className="aln-peek-controls">
        <label>
          <input type="checkbox" checked={scrub} onChange={(e) => toggleScrub(e.target.checked)} /> Scrub the cycle
        </label>
        <input
          className="aln-peek-scrubber"
          type="range"
          min={0}
          max={0.999}
          step={0.001}
          value={phase}
          disabled={!scrub}
          onChange={(e) => setPhase(Number(e.target.value))}
        />
        <span>
          {(phase * 100).toFixed(1)}% · {phaseLabel(phase)}
        </span>
      </div>

      <div
        ref={stageRef}
        key={run}
        className={`aln-peek-stage aln-peek-stage--${stage}${debug ? " aln-peek-debug" : ""}`}
        style={{ zoom: magnify }}
        data-peek-stage
      >
        <div className="aln-peek-card peek-pet-host" style={{ marginTop: clearance }} data-peek-card="pair">
          <PeekingPet {...peekingCats.orange} {...common} delay={orangeDelay} x={32} className="aln-peek-orange" />
          <PeekingPet
            {...peekingCats.gray}
            {...common}
            delay={grayDelay}
            x={`calc(100% - 32px - ${width}px)`}
            className="aln-peek-gray"
          />
          <h3>Your pets</h3>
          <p>Cats peek over the card's top edge. The card's layout ignores them.</p>
          <button type="button">A real button stays clickable</button>
        </div>

        <div className="aln-peek-card peek-pet-host" style={{ marginTop: clearance }} data-peek-card="wide">
          <PeekingPet
            {...peekingCats.gray}
            {...common}
            x={`calc(78% - ${width / 2}px)`}
            delay={grayDelay + 1.1}
            className="aln-peek-wide"
          />
          <h3>Anywhere along the edge</h3>
          <p>
            Same gray cat placed with <code>x="calc(78% - {width / 2}px)"</code>.
          </p>
        </div>
      </div>
    </section>
  );
}
