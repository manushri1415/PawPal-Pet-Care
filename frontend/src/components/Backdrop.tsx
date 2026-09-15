import './Backdrop.css';
import type { CSSProperties } from 'react';
import { BACKDROP } from '../art/backdrop';
import type { BackdropLayer } from '../art/backdrop';

function layerStyle(layer: BackdropLayer): CSSProperties {
  return {
    backgroundImage: `url("${layer.src}")`,
    ...(layer.size !== undefined && { '--pp-backdrop-size': `${layer.size}px` }),
    ...(layer.opacity !== undefined && { '--pp-backdrop-opacity': layer.opacity }),
    ...(layer.blend !== undefined && { '--pp-backdrop-blend': layer.blend }),
  } as CSSProperties;
}

/**
 * Fixed, non-interactive layers between the page colour and the app content:
 * an optional repeating pet pattern and an optional paper/grain texture,
 * each configured in art/backdrop.ts. Renders nothing while both are off.
 */
export function Backdrop() {
  const { pattern, texture } = BACKDROP;
  if (!pattern && !texture) return null;

  return (
    <div className="pp-backdrop" aria-hidden="true">
      {pattern && <div className="pp-backdrop__layer pp-backdrop__pattern" style={layerStyle(pattern)} />}
      {texture && <div className="pp-backdrop__layer pp-backdrop__texture" style={layerStyle(texture)} />}
    </div>
  );
}
