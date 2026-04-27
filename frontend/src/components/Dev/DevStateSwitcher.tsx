/* DEUDA TÉCNICA — eliminar antes de la release 1.
   ─────────────────────────────────────────────────────────────────
   Switcher flotante que fuerza el estado del Cockpit (warmup,
   degraded, splus, error, scanning, loading) escribiendo en
   `useEngineStore.stateOverride`. Útil para previsualizar las
   variantes sin necesitar levantar el backend ni reproducir las
   condiciones reales que las disparan.

   - Solo se monta en builds DEV (`import.meta.env.DEV`).
   - El override del engine store tiene prioridad absoluta en
     `useCockpitState`.
   - Para eliminar pre-release: borrar este archivo + la carpeta
     `Dev/`, quitar la prop `stateOverride` de `engine.ts` y la
     condición de override de `StateToast.tsx`. */

import "./dev-state-switcher.css";
import { type CockpitStateName, useEngineStore } from "@/stores/engine";
import { useState } from "react";

const STATES: Array<{ value: CockpitStateName | null; label: string }> = [
  { value: null, label: "real" },
  { value: "normal", label: "normal" },
  { value: "warmup", label: "warmup" },
  { value: "degraded", label: "degraded" },
  { value: "splus", label: "S+" },
  { value: "error", label: "error" },
  { value: "scanning", label: "scanning" },
  { value: "loading", label: "loading" },
];

export function DevStateSwitcher() {
  if (!import.meta.env.DEV) return null;
  return <DevStateSwitcherInner />;
}

function DevStateSwitcherInner() {
  const stateOverride = useEngineStore((s) => s.stateOverride);
  const setStateOverride = useEngineStore((s) => s.setStateOverride);
  const [collapsed, setCollapsed] = useState(false);

  if (collapsed) {
    return (
      <button
        type="button"
        className="dev-switcher dev-switcher--collapsed"
        onClick={() => setCollapsed(false)}
        title="Mostrar dev state switcher"
      >
        ⚙
      </button>
    );
  }

  return (
    <aside className="dev-switcher" aria-label="dev state switcher">
      <header className="dev-switcher__head">
        <span>state preview</span>
        <button
          type="button"
          className="dev-switcher__close"
          onClick={() => setCollapsed(true)}
          aria-label="colapsar"
        >
          ×
        </button>
      </header>
      <div className="dev-switcher__row">
        {STATES.map((s) => {
          const active = stateOverride === s.value;
          return (
            <button
              type="button"
              key={s.label}
              className={active ? "dev-pill is-active" : "dev-pill"}
              onClick={() => setStateOverride(s.value)}
            >
              {s.label}
            </button>
          );
        })}
      </div>
      <p className="dev-switcher__hint">DEV only · se elimina pre-release</p>
    </aside>
  );
}
