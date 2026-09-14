/**
 * Decorative page-background layers. They sit between the cream page colour
 * and the app content (see components/Backdrop.tsx), never receive pointer
 * events, and are off until a file is registered here — there is no stand-in
 * pattern.
 *
 * To enable the pet pattern:
 *   1. Drop it in src/assets/patterns/ (WebP or SVG, seamless tile).
 *   2. Import it below and set `pattern`.
 * The paper/grain texture works the same way via `texture`. Opacity and tile
 * size are independent per layer; tune them here or override the CSS custom
 * properties (`--pp-backdrop-*`, defined in styles/tokens.css) in devtools.
 */

// import petPattern from '../assets/patterns/pet-pattern.webp';
// import paperGrain from '../assets/textures/paper-grain.webp';

export interface BackdropLayer {
  src: string;
  /** Tile width in CSS px (height follows the image's aspect ratio). */
  size?: number;
  /** 0–1. Keep patterns around 0.04–0.1 so cards stay the focus. */
  opacity?: number;
  /** CSS blend mode; `multiply` lets a light texture darken the cream a touch. */
  blend?: 'normal' | 'multiply' | 'soft-light' | 'overlay';
}

export const BACKDROP: { pattern: BackdropLayer | null; texture: BackdropLayer | null } = {
  pattern: null,
  // pattern: { src: petPattern, size: 360, opacity: 0.07 },
  texture: null,
  // texture: { src: paperGrain, size: 240, opacity: 0.06, blend: 'multiply' },
};
