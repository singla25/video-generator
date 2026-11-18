import type { ReactNode } from 'react';

interface Props {
  label: string;
  children: ReactNode;
  className?: string;
}

/** Horizontally scrolling container that keyboard users can focus and scroll. */
export function ScrollRegion({ label, children, className = '' }: Props) {
  return (
    <div
      role="region"
      tabIndex={0}
      aria-label={label}
      className={`overflow-x-auto focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald ${className}`.trim()}
    >
      {children}
    </div>
  );
}
