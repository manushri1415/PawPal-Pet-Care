import './Tag.css';
import type { ReactNode } from 'react';

export function Tag({
  children,
  tone = 'terracotta',
}: {
  children: ReactNode;
  tone?: 'terracotta' | 'lavender' | 'sage';
}) {
  return <span className={`pp-tag pp-tag-${tone}`}>{children}</span>;
}
