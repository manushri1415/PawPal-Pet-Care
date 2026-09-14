import { useEffect, useRef, useState } from "react";
import { SidePeekingPet } from "../../components/SidePeekingPet";
import { sidePeekingCat } from "../../assets/pets";

/**
 * TEMPORARY development-only demo of <SidePeekingPet>. The scrubber pauses the
 * CSS animations through the Web Animations API — a test-page convenience
 * only; the component itself uses no JS timing.
 */

type Stage = "cream" | "white" | "dark";

const PHASES: [number, string][] = [
  [0.38, "hidden"],
  [0.455, "sliding out"],
  [0.49, "settling"],
  [0.58, "resting"],
  [0.588, "reaching for the edge"],
  [0.7, "holding the edge"],
  [0.708, "letting go"],
  [0.82, "resting"],
  [0.835, "push-off"],
  [0.9, "sliding back"],
  [1, "hidden"],
];

function phaseLabel(p: number) {
  return PHASES.find(([end]) => p < end)?.[1] ?? "hidden";
}

export function SidePeekDemo() {
  const [width, setWidth] = useState(120);
  const [hop, setHop] = useState(0);
  const [duration, setDuration] = useState(12);
  const [delay, setDelay] = useState(sidePeekingCat.delay);
  const [stage, setStage] = useState<Stage>("cream");
  const [magnify, setMagnify] = useState(1);
  const [still, setStill] = useState(false);
  const [debug, setDebug] = useState(false);
  const [scrub, setScrub] = useState(false);
  const [phase, setPhase] = useState(0.65);
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
  }, [scrub, phase, run, width, hop, duration, delay, still, magnify]);

  const toggleScrub = (on: boolean) => {
    setScrub(on);
    if (!on) setRun((r) => r + 1);
  };

  // x = 0: the cat's cut side covers the card's 1px border, so no light line shows between card and cat.
  const common = { width, hopHeight: hop, duration, x: 0, y: 14, animated: !still };
  // Room beside each card for the part of the cat that comes out (plus the overshoot), and a card tall enough for it.
  const { geometry } = sidePeekingCat;
  const room = Math.ceil(width * (1 - geometry.edge / geometry.width) + hop + 24);
  const cardHeight = Math.ceil((width * geometry.height) / geometry.width) + common.y;

  return (
    <section className="aln-family aln-side" data-side-demo>
      <h2>Side-peeking gray cat · peek around the edge</h2>
      <p className="aln-meta">
        The cat hides behind the card's side edge, slides out, grabs the edge with its paw, lets go and slides back.
        The wall line drawn into the frames stays hidden behind the edge. First peek at {delay}s, then every{" "}
        {duration}s; the left card's cat starts {(duration / 2).toFixed(1)}s later.
      </p>

      <div className="aln-peek-controls">
        <label>
          Width{" "}
          <input type="range" min={70} max={260} value={width} onChange={(e) => setWidth(Number(e.target.value))} />{" "}
          {width}px
        </label>
        <label>
          Overshoot{" "}
          <input type="range" min={0} max={16} value={hop} onChange={(e) => setHop(Number(e.target.value))} /> {hop}px
        </label>
        <label>
          Cycle{" "}
          <input type="range" min={8} max={20} step={0.5} value={duration} onChange={(e) => setDuration(Number(e.target.value))} />{" "}
          {duration}s
        </label>
        <label>
          Delay{" "}
          <input type="number" min={0} max={30} step={0.1} value={delay} onChange={(e) => setDelay(Number(e.target.value) || 0)} />s
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
        className={`aln-peek-stage aln-peek-stage--${stage}${debug ? " aln-side-debug" : ""}`}
        style={{ zoom: magnify }}
        data-side-stage
      >
        <div
          className="aln-peek-card aln-side-card"
          style={{ marginRight: room, minHeight: cardHeight }}
          data-side-card="right"
        >
          <SidePeekingPet {...sidePeekingCat} {...common} delay={delay} className="aln-side-right" />
          <h3>Right edge</h3>
          <p>The cat comes out from behind the card's right edge. The card's layout ignores it.</p>
          <button type="button">A real button stays clickable</button>
        </div>
        <div
          className="aln-peek-card aln-side-card"
          style={{ marginLeft: room, minHeight: cardHeight }}
          data-side-card="left"
        >
          <SidePeekingPet
            {...sidePeekingCat}
            {...common}
            side="left"
            delay={delay + duration / 2}
            className="aln-side-left"
          />
          <h3>Left edge</h3>
          <p>
            Same cat with <code>side="left"</code> (mirrored).
          </p>
        </div>
      </div>
    </section>
  );
}
