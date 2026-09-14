import './PetArt.css';
import type { CSSProperties } from 'react';
import { DEFAULT_VARIANT, resolveArt } from '../art/registry';
import type { ArtSlot } from '../art/registry';

/**
 * Renders the artwork registered for a slot (art/registry.ts), or nothing at
 * all if the slot is empty — so a section can keep its hook in place without
 * showing a placeholder. All frames are stacked <img>s in one box; the CSS in
 * PetArt.css handles placement variants and the opacity-only animations.
 *
 * Size and position are controlled from the slot's own CSS via custom
 * properties (`--pp-art-size`, `--pp-art-overlap`, `--pp-art-overhang`, …);
 * pass `className` to hook them up.
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
  const resolved = resolveArt(slot);
  if (!resolved) return null;

  const { spec } = resolved;
  const variant = spec.variant ?? DEFAULT_VARIANT[resolved.slot];
  const frames = [spec.src, ...(spec.frames ?? [])];
  const decorative = !spec.alt;

  const classes = [
    'pp-art',
    `pp-art--${variant}`,
    `pp-art--frames-${Math.min(frames.length, 3)}`,
    ...(spec.animations ?? []).map((animation) => `pp-art--anim-${animation}`),
    className,
  ]
    .filter(Boolean)
    .join(' ');

  const vars = {
    '--pp-art-w': spec.width,
    '--pp-art-h': spec.height,
    ...(spec.period !== undefined && { '--pp-art-period': `${spec.period}s` }),
    ...(spec.delay !== undefined && { '--pp-art-delay': `${spec.delay}s` }),
    ...style,
  } as CSSProperties;

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
            />
          ))}
        </span>
      </span>
    </span>
  );
}
