import { formatEtDate, formatEtTime, useNow } from "@/lib/clock";
import { useEngineStore } from "@/stores/engine";
import type { ReactNode } from "react";

interface TopBarProps {
  children: ReactNode;
}

export function TopBar({ children }: TopBarProps) {
  const now = useNow();
  const ws = useEngineStore((s) => s.ws);
  const liveClass = ws === "connected" ? "topbar__live" : `topbar__live topbar__live--${ws}`;
  const liveLabel = ws === "connected" ? "live" : ws === "connecting" ? "linking" : "offline";

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
        <span className={liveClass}>{liveLabel}</span>
        <span className="topbar__clock">{formatEtTime(now)}</span>
        <span className="topbar__date">{formatEtDate(now)}</span>
      </div>
    </header>
  );
}
