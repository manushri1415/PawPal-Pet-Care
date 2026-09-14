import './Button.css';
import type { ButtonHTMLAttributes } from 'react';

export type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger';

/**
 * `ghost` is a borderless quiet action (row/card actions); `danger` is its
 * destructive counterpart. `iconOnly` squares the button for a lone icon —
 * always pair it with an `aria-label`.
 */
export function Button({
  variant = 'primary',
  size = 'md',
  iconOnly = false,
  className,
  ...rest
}: {
  variant?: ButtonVariant;
  size?: 'sm' | 'md';
  iconOnly?: boolean;
} & ButtonHTMLAttributes<HTMLButtonElement>) {
  const classes = [
    'pp-button',
    `pp-button--${variant}`,
    size === 'sm' && 'pp-button--sm',
    iconOnly && 'pp-button--icon',
    className,
  ]
    .filter(Boolean)
    .join(' ');
  return <button className={classes} {...rest} />;
}
