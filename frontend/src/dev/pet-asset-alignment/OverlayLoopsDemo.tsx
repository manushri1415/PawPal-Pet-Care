import { useEffect, useRef, useState } from "react";
import { PetOverlayLoop, type OverlayLoopTiming, type OverlayStep } from "../../components/PetOverlayLoop";
import { overlayLoops } from "../../assets/pets";

/**
 * TEMPORARY development-only demos of <PetOverlayLoop>: the sleeping dog's
 * Z's and the resting cat's tail. The scrubber and the live readout use the
 * Web Animations API and getComputedStyle — test-page conveniences only; the
 * component itself runs on CSS keyframes.
 */

type Stage = "cream" | "white" | "dark";
type Preset = (typeof overlayLoops)[keyof typeof overlayLoops];
type Return = "middle" | "straight";

interface Readout {
  bodyOpacity: number;
  lowestBodyOpacity: number;
  bodyTransform: string;
  bodyAnimations: number;
  bodyDrift: number;
  layers: number[];
}

interface RoleHolds {
  rest: number;
  middle: number;
  peak: number;
}

/** Every order of the three overlays, then every ordered pair. The first overlay is the resting one. */
const SEQUENCES: number[][] = [
  [0, 1, 2],
  [0, 2, 1],
  [1, 0, 2],
  [1, 2, 0],
  [2, 0, 1],
  [2, 1, 0],
  [0, 1],
  [0, 2],
  [1, 0],
  [1, 2],
  [2, 0],
  [2, 1],
];

/** Steps for a flick: rest on the first overlay, visit the others, come back. */
function flickSteps(frames: number[], ret: Return, holds: RoleHolds): OverlayStep[] {
  if (frames.length === 2) {
    return [
      { layer: frames[0], hold: holds.rest },
      { layer: frames[1], hold: holds.peak },
    ];
  }
  const [rest, middle, peak] = frames;
  const steps: OverlayStep[] = [
    { layer: rest, hold: holds.rest },
    { layer: middle, hold: holds.middle },
    { layer: peak, hold: holds.peak },
  ];
  if (ret === "middle") steps.push({ layer: middle, hold: holds.middle });
  return steps;
}

function describe(timing: OverlayLoopTiming, name: (layer: number | null) => string, t: number) {
  let at = 0;
  for (const [k, step] of timing.steps.entries()) {
    const next = timing.steps[(k + 1) % timing.steps.length];
    if (t < at + step.hold) return `holding ${name(step.layer)}`;
    at += step.hold;
    if (t < at + timing.fade) return `${name(step.layer)} → ${name(next.layer)}`;
    at += timing.fade;
  }
  return `holding ${name(timing.steps[0].layer)}`;
}

interface LoopDemoProps {
  title: string;
  intro: string;
  preset: Preset;
  names: string[];
  /** Label for a step with no overlay. */
  emptyName?: string;
  defaultWidth: number;
  fadeMax: number;
  /** Offer flick orders of 3 or 2 overlays (resting on the first) instead of per-step holds. */
  flick?: boolean;
  demoId: string;
}

function LoopDemo({
  title,
  intro,
  preset,
  names,
  emptyName = "nothing",
  defaultWidth,
  fadeMax,
  flick,
  demoId,
}: LoopDemoProps) {
  const presetSteps: OverlayStep[] = preset.timing.steps;
  const [width, setWidth] = useState(defaultWidth);
  const [fade, setFade] = useState(preset.timing.fade);
  const [holds, setHolds] = useState(presetSteps.map((s) => s.hold));
  const [sequence, setSequence] = useState(0);
  const [ret, setRet] = useState<Return>("middle");
  const [roleHolds, setRoleHolds] = useState<RoleHolds>({
    rest: presetSteps[0]?.hold ?? 6,
    middle: presetSteps[1]?.hold ?? 0.15,
    peak: presetSteps[2]?.hold ?? 0.45,
  });
  const [still, setStill] = useState(false);
  const [stage, setStage] = useState<Stage>("cream");
  const [magnify, setMagnify] = useState(1);
  const [showBox, setShowBox] = useState(false);
  const [scrub, setScrub] = useState(false);
  const [phase, setPhase] = useState(0);
  const [run, setRun] = useState(0);
  const [readout, setReadout] = useState<Readout | null>(null);
  const stageRef = useRef<HTMLDivElement>(null);

  const frames = SEQUENCES[sequence];
  const steps = flick
    ? flickSteps(frames, ret, roleHolds)
    : presetSteps.map((s, k) => ({ layer: s.layer, hold: holds[k] }));
  const timing: OverlayLoopTiming = { ...preset.timing, fade, steps };
  const cycle = steps.reduce((sum, s) => sum + s.hold + fade, 0);
  const timingKey = JSON.stringify(timing);
  const name = (layer: number | null) => (layer === null ? emptyName : names[layer]);
  const loopText = [...steps, steps[0]].map((s) => name(s.layer)).join(" → ");
  const stillLayer = flick ? frames[0] : preset.stillLayer;

  useEffect(() => {
    const root = stageRef.current;
    if (!root || !scrub) return;
    for (const animation of root.getAnimations({ subtree: true })) {
      const t = animation.effect?.getTiming();
      const duration = Number(t?.duration);
      if (!t || !Number.isFinite(duration)) continue;
      animation.pause();
      animation.currentTime = Number(t.delay ?? 0) + (phase + 1) * duration;
    }
  }, [scrub, phase, run, width, timingKey, still, magnify]);

  // Live proof that the body never changes: its opacity, transform, animations and position in the box.
  useEffect(() => {
    const root = stageRef.current;
    const base = root?.querySelector<HTMLImageElement>(".pet-loop__base");
    const box = root?.querySelector<HTMLElement>(".pet-loop");
    if (!root || !base || !box) return;
    const layers = [...root.querySelectorAll<HTMLImageElement>(".pet-loop__layer")];
    const offset = () => {
      const b = base.getBoundingClientRect();
      const c = box.getBoundingClientRect();
      return [b.left - c.left, b.top - c.top, b.width - c.width, b.height - c.height];
    };
    const start = offset();
    let lowest = 1;
    let drift = 0;
    let last = 0;
    let frame = 0;
    const tick = (now: number) => {
      const style = getComputedStyle(base);
      const opacity = Number(style.opacity);
      lowest = Math.min(lowest, opacity);
      drift = Math.max(drift, ...offset().map((v, i) => Math.abs(v - start[i])));
      if (now - last > 150) {
        last = now;
        setReadout({
          bodyOpacity: opacity,
          lowestBodyOpacity: lowest,
          bodyTransform: style.transform,
          bodyAnimations: base.getAnimations().length,
          bodyDrift: drift,
          layers: layers.map((l) => Number(getComputedStyle(l).opacity)),
        });
      }
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [run, width, timingKey, still, magnify]);

  const toggleScrub = (on: boolean) => {
    setScrub(on);
    if (!on) setRun((r) => r + 1);
  };

  const holdInput = (value: number, onChange: (v: number) => void) => (
    <input
      type="number"
      min={0}
      max={30}
      step={0.05}
      value={value}
      onChange={(e) => onChange(Math.max(0, Number(e.target.value) || 0))}
    />
  );

  return (
    <section className="aln-family aln-loop" data-loop-demo={demoId}>
      <h2>{title}</h2>
      <p className="aln-meta">{intro}</p>

      <div className="aln-peek-controls">
        <label>
          Width{" "}
          <input type="range" min={80} max={640} value={width} onChange={(e) => setWidth(Number(e.target.value))} />{" "}
          {width}px
        </label>
        <label>
          Fade{" "}
          <input type="range" min={0} max={fadeMax} step={0.01} value={fade} onChange={(e) => setFade(Number(e.target.value))} />{" "}
          {Math.round(fade * 1000)}ms
        </label>
        {flick ? (
          <>
            <label>
              Tails{" "}
              <select value={sequence} onChange={(e) => setSequence(Number(e.target.value))} data-loop-sequence-select={demoId}>
                <optgroup label="3 tails (rest on the first)">
                  {SEQUENCES.map((seq, i) =>
                    seq.length === 3 ? (
                      <option key={i} value={i}>
                        {seq.map((layer) => names[layer]).join(" → ")}
                        {i === 0 ? " (default)" : ""}
                      </option>
                    ) : null,
                  )}
                </optgroup>
                <optgroup label="2 tails (rest on the first)">
                  {SEQUENCES.map((seq, i) =>
                    seq.length === 2 ? (
                      <option key={i} value={i}>
                        {[...seq, seq[0]].map((layer) => names[layer]).join(" → ")}
                      </option>
                    ) : null,
                  )}
                </optgroup>
              </select>
            </label>
            {frames.length === 3 && (
              <label>
                Return{" "}
                <select value={ret} onChange={(e) => setRet(e.target.value as Return)}>
                  <option value="middle">back through {names[frames[1]]}</option>
                  <option value="straight">straight back to {names[frames[0]]}</option>
                </select>
              </label>
            )}
            <label>
              Rest on {names[frames[0]]} {holdInput(roleHolds.rest, (v) => setRoleHolds((h) => ({ ...h, rest: v })))}s
            </label>
            {frames.length === 3 && (
              <label>
                Hold {names[frames[1]]} {holdInput(roleHolds.middle, (v) => setRoleHolds((h) => ({ ...h, middle: v })))}s
              </label>
            )}
            <label>
              Hold {names[frames[frames.length - 1]]}{" "}
              {holdInput(roleHolds.peak, (v) => setRoleHolds((h) => ({ ...h, peak: v })))}s
            </label>
          </>
        ) : (
          steps.map((step, k) => (
            <label key={k}>
              Hold {name(step.layer)}
              {steps.findIndex((s) => s.layer === step.layer) !== k ? " (again)" : ""}{" "}
              {holdInput(holds[k], (v) => setHolds((h) => h.map((old, i) => (i === k ? v : old))))}s
            </label>
          ))
        )}
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
          <input type="checkbox" checked={showBox} onChange={(e) => setShowBox(e.target.checked)} /> Show canvas box
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
          {(phase * cycle).toFixed(2)}s of {cycle.toFixed(2)}s · {describe(timing, name, phase * cycle)}
        </span>
      </div>

      <p className="aln-meta" data-loop-sequence={demoId}>
        Loop: {loopText} · first change after {preset.timing.delay}s
      </p>

      <div
        ref={stageRef}
        key={run}
        className={`aln-peek-stage aln-peek-stage--${stage}${showBox ? " aln-loop-debug" : ""}`}
        style={{ zoom: magnify }}
        data-loop-stage={demoId}
      >
        <div className="aln-peek-card aln-loop-card">
          <PetOverlayLoop {...preset} timing={timing} stillLayer={stillLayer} width={width} animated={!still} />
        </div>
      </div>

      {readout && (
        <p className="aln-loop-readout" data-loop-readout={demoId}>
          Body: opacity {readout.bodyOpacity.toFixed(3)} (lowest seen {readout.lowestBodyOpacity.toFixed(3)}) ·
          transform {readout.bodyTransform} · animations on body {readout.bodyAnimations} · drift in box{" "}
          {readout.bodyDrift.toFixed(2)}px
          <br />
          Overlays: {readout.layers.map((o, i) => `${names[i]} ${o.toFixed(2)}`).join(" · ")}
        </p>
      )}
    </section>
  );
}

export function OverlayLoopsDemo() {
  return (
    <>
      <LoopDemo
        demoId="dog"
        title="Sleeping dog · Z's"
        intro="The dog (no Z's) is one image that never animates. The Z's appear one by one — Z → ZZ → ZZZ — hold for a moment, then all fade out and it starts again. Each Z layer contains the one before it, so only the new Z fades in."
        preset={overlayLoops.sleepingDog}
        names={["Z", "ZZ", "ZZZ"]}
        emptyName="no Z's"
        defaultWidth={240}
        fadeMax={1}
      />
      <LoopDemo
        demoId="tail"
        title="Resting orange cat · tail flick"
        intro="The cat's body is one image that never animates. Only the tail changes: a long rest, then a quick flick with short crossfades. Pick any order of the three tails, or just two of them; the first one is the resting pose."
        preset={overlayLoops.restingOrangeCat}
        names={["tail-1", "tail-2", "tail-3"]}
        defaultWidth={280}
        fadeMax={0.4}
        flick
      />
    </>
  );
}
