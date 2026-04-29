import type { ReactElement } from "react";

export type PilotState = "ok" | "warn" | "err" | "pend";

interface PilotProps {
  state?: PilotState;
  className?: string;
}

/* Indicador de estado tipo dot 7×7 con glow. Heredado de los tokens
   de tier del Cockpit (`pilot-ok` verde · `pilot-warn` ámbar · etc).
   `ok` es el default — no requiere modificador. */
export function Pilot({ state = "ok", className }: PilotProps): ReactElement {
  const cls = state === "ok" ? "pilot" : `pilot is-${state}`;
  return <span className={className ? `${cls} ${className}` : cls} aria-hidden="true" />;
}
