import { useLayoutEffect, useRef } from 'react';

/**
 * Sliding highlight for a row of options (the Today / Health records pill,
 * the To do / Done / All control). Measures whichever child of the host
 * currently matches `activeSelector` and writes its box to
 * `--pp-indicator-x / -y / -w / -h` on the host, where a `::before`
 * pseudo-element draws the highlight and transitions between positions —
 * so the highlight slides to the option instead of jumping.
 *
 * Re-measures when `activeKey` changes and whenever the host or one of its
 * children resizes (font swap, wrapping on narrow screens). The host needs
 * `position: relative`; the CSS turns the transition on only once
 * `pp-indicator--ready` is present, so nothing slides in on first paint.
 */
export function useSlidingIndicator<T extends HTMLElement>(activeKey: unknown, activeSelector: string) {
  const ref = useRef<T>(null);

  useLayoutEffect(() => {
    const host = ref.current;
    if (!host) return;

    const measure = () => {
      const active = host.querySelector<HTMLElement>(activeSelector);
      if (!active) {
        host.style.setProperty('--pp-indicator-w', '0px');
        return;
      }
      host.style.setProperty('--pp-indicator-x', `${active.offsetLeft}px`);
      host.style.setProperty('--pp-indicator-y', `${active.offsetTop}px`);
      host.style.setProperty('--pp-indicator-w', `${active.offsetWidth}px`);
      host.style.setProperty('--pp-indicator-h', `${active.offsetHeight}px`);
      host.classList.add('pp-indicator--ready');
    };

    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(host);
    for (const child of host.children) observer.observe(child);
    return () => observer.disconnect();
  }, [activeKey, activeSelector]);

  return ref;
}
