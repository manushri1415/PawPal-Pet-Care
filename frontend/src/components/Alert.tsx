import './Alert.css';
import type { ReactNode } from 'react';

export function Alert({
  tone,
  children,
}: {
  tone: 'info' | 'success' | 'warning' | 'error';
  children: ReactNode;
}) {
  return <div className={`pp-alert pp-alert--${tone}`} role="alert">{children}</div>;
}
