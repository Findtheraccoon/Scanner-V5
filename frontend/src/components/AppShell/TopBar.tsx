import type { ReactNode } from "react";

interface TopBarProps {
  children: ReactNode;
}

export function TopBar({ children }: TopBarProps) {
  return (
    <header className="topbar">
      <div className="topbar__brand">
        <span className="brand__text">
          <span className="brand__name">scanner</span>
          <span className="brand__sub">v5.0.0-dev</span>
        </span>
      </div>
      {children}
      <div className="topbar__meta">
        <span className="topbar__live">live</span>
        <span className="topbar__clock">14:30:04 ET</span>
        <span className="topbar__date">vie 25 abr 2026</span>
      </div>
    </header>
  );
}
