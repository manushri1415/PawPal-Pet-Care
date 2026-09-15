import './PetArt.css';
import { useState } from 'react';
import type { CSSProperties } from 'react';
import { DEFAULT_VARIANT, resolveArt } from '../art/registry';
import type { ArtSlot } from '../art/registry';
import { PeekingPet } from './PeekingPet';

/**
 * Renders the artwork registered for a slot (art/registry.ts), or nothing at
 * all if the slot is empty — so a section can keep its hook in place without
 * showing a placeholder. All images are stacked <img>s in one box; the CSS in
 * PetArt.css handles placement variants and the opacity-only animations.
 *
 * Two shapes of family: `frames` (complete alternate drawings, one visible at
 * a time) and `layers` (a body that always shows, plus overlay-only files
 * that take turns on top of it).
 *
 * The `hop` animation (a peek-top pet that appears and disappears) is handed
 * to PeekingPet, which clips the pet at the edge it hops over.
 *
 * Size and position are controlled from the slot's own CSS via custom
 * properties (`--pp-art-size`, `--pp-art-overlap`, `--pp-art-overhang`, …;
 * `--peek-pet-*` for `hop`); pass `className` to hook them up.
 */
export function PetArt({
  slot,
  className,
  style,
}: {
  slot: ArtSlot | ArtSlot[];
  className?: string;
  style?: CSSProperties;
}) {
  // The resting frame / body has arrived (or failed) — drives the `fade`
  // animation, which is a transition on this class rather than a mount-time
  // keyframe so it happens when the picture actually appears.
  const [ready, setReady] = useState(false);

  const resolved = resolveArt(slot);
  if (!resolved) return null;

  const { spec } = resolved;
  const variant = spec.variant ?? DEFAULT_VARIANT[resolved.slot];
  const animations = spec.animations ?? [];

  if (variant === 'peek-top' && animations.includes('hop')) {
    return (
      <span style={{ display: 'contents' }} data-art-slot={resolved.slot}>
        <PeekingPet
          openFrame={spec.src}
          winkFrame={spec.frames?.[0] ?? spec.src}
          geometry={{ width: spec.width, height: spec.height, bodyBottom: spec.edge ?? spec.height }}
          delay={spec.delay}
          duration={spec.period}
          className={['pp-art-hop', className].filter(Boolean).join(' ')}
          style={style}
        />
      </span>
    );
  }

  const layers = spec.layers ?? [];
  const layered = layers.length > 0;
  const frames = layered ? [spec.src] : [spec.src, ...(spec.frames ?? [])];
  const still = Math.min(spec.still ?? 0, Math.max(layers.length - 1, 0));
  const decorative = !spec.alt;

  const classes = [
    'pp-art',
    `pp-art--${variant}`,
    layered ? `pp-art--layered pp-art--layers-${Math.min(layers.length, 3)}` : `pp-art--frames-${Math.min(frames.length, 3)}`,
    ...animations.map((animation) => `pp-art--anim-${animation}`),
    ready && 'pp-art--ready',
    className,
  ]
    .filter(Boolean)
    .join(' ');

  // `edge` becomes a unitless fraction along the axis the variant cares about.
  const edge =
    spec.edge === undefined
      ? undefined
      : variant === 'peek-side'
        ? spec.edge / spec.width
        : spec.edge / spec.height;

  const vars = {
    '--pp-art-w': spec.width,
    '--pp-art-h': spec.height,
    ...(edge !== undefined && { '--pp-art-edge': edge }),
    ...(spec.period !== undefined && { '--pp-art-period': `${spec.period}s` }),
    ...(spec.delay !== undefined && { '--pp-art-delay': `${spec.delay}s` }),
    ...style,
  } as CSSProperties;

  const markReady = () => setReady(true);

  return (
    <span
      className={classes}
      style={vars}
      data-art-slot={resolved.slot}
      aria-hidden={decorative || undefined}
      role={decorative ? undefined : 'img'}
      aria-label={spec.alt}
    >
      <span className="pp-art__motion">
        <span className="pp-art__stage">
          {frames.map((src, index) => (
            <img
              key={src}
              src={src}
              alt=""
              draggable={false}
              className={index === 0 ? 'pp-art__frame pp-art__frame--base' : 'pp-art__frame'}
              onLoad={index === 0 ? markReady : undefined}
              onError={index === 0 ? markReady : undefined}
            />
          ))}
          {layered && (
            <span className="pp-art__layers">
              {layers.map((src, index) => (
                <img
                  key={src}
                  src={src}
                  alt=""
                  draggable={false}
                  className={index === still ? 'pp-art__frame pp-art__frame--base' : 'pp-art__frame'}
                />
              ))}
            </span>
          )}
        </span>
      </span>
    </span>
  );
}
