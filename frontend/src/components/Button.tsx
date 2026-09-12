import './Button.css';
import type { ButtonHTMLAttributes } from 'react';

export function Button({
  variant = 'primary',
  className,
  ...rest
}: { variant?: 'primary' | 'secondary' } & ButtonHTMLAttributes<HTMLButtonElement>) {
  const classes = ['pp-button', `pp-button--${variant}`, className].filter(Boolean).join(' ');
  return <button className={classes} {...rest} />;
}
