import type { ReactNode } from "react";

interface CardProps {
  title: string;
  note?: string;
  actions?: ReactNode;
  className?: string;
  children: ReactNode;
}

export function Card({ title, note, actions, className = "", children }: CardProps) {
  return (
    <section
      className={`relative rounded-panel border border-line bg-gradient-to-b from-raised to-panel shadow-panel ${className}`}
      aria-label={title}
    >
      <header className="flex flex-wrap items-baseline gap-x-3 gap-y-1 px-4 pt-3.5">
        <h2 className="text-[14px] font-semibold text-ink">{title}</h2>
        {note && <span className="text-xs text-muted">{note}</span>}
        {actions && <div className="ml-auto">{actions}</div>}
      </header>
      {children}
    </section>
  );
}
