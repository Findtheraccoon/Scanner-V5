import type { SignalPayload } from "@/api/types";
import { useEngineStore } from "@/stores/engine";
import { useScanningStore } from "@/stores/scanning";
import { useSignalsStore } from "@/stores/signals";
import { useSlotsStore } from "@/stores/slots";
import { useEffect, useState } from "react";
import { useEffectiveSlot } from "./useEffectiveSlot";

export type CockpitState =
  | "normal"
  | "warmup"
  | "degraded"
  | "splus"
  | "error"
  | "scanning"
  | "loading";

/* Resuelve el estado activo del Cockpit según los stores. Prioridad:
   error (data engine red) → splus (señal S+ reciente) → degraded (slot
   con ENG-060) → warmup (slot warming_up) → scanning (slot con scan
   en curso) → normal. El estado "loading" no se resuelve aquí: lo
   maneja el AppShell según las queries iniciales del backend. El
   override del DevStateSwitcher (dev-only) tiene prioridad absoluta. */
export function useCockpitState(): { state: CockpitState; ticker: string | null } {
  const engineData = useEngineStore((s) => s.data);
  const stateOverride = useEngineStore((s) => s.stateOverride);
  const selectedId = useSlotsStore((s) => s.selectedSlotId);
  const latestSignal = useSignalsStore((s) => s.latest);
  const effective = useEffectiveSlot(selectedId);
  const scanningSelected = useScanningStore((s) => s.active.has(selectedId));

  const ticker = effective.ticker;
  const isSplusFresh = isFreshSplus(latestSignal);

  if (stateOverride !== null) return { state: stateOverride, ticker };
  if (engineData === "red") return { state: "error", ticker };
  if (isSplusFresh) return { state: "splus", ticker: latestSignal?.ticker ?? ticker };
  if (effective.status === "degraded") return { state: "degraded", ticker };
  if (effective.status === "warming_up") return { state: "warmup", ticker };
  if (scanningSelected) return { state: "scanning", ticker };
  return { state: "normal", ticker };
}

function isFreshSplus(sig: SignalPayload | null): boolean {
  if (!sig || sig.conf !== "S+") return false;
  const ts = Date.parse(sig.computed_at);
  if (Number.isNaN(ts)) return false;
  return Date.now() - ts < 30_000;
}

interface StateToastsProps {
  state: CockpitState;
  ticker: string | null;
}

export function StateToasts({ state, ticker }: StateToastsProps) {
  const errCode = useEngineStore((s) => s.errorCodes.data);
  const slot = useSlotsStore((s) => s.slots.find((sl) => sl.slot_id === s.selectedSlotId));

  const [splusTime, setSplusTime] = useState<string>("");
  const latestSignal = useSignalsStore((s) => s.latest);

  useEffect(() => {
    if (state !== "splus" || !latestSignal) return;
    const d = new Date(latestSignal.computed_at);
    setSplusTime(
      `${d.getUTCHours().toString().padStart(2, "0")}:${d.getUTCMinutes().toString().padStart(2, "0")} ET`,
    );
  }, [state, latestSignal]);

  const t = ticker ?? "—";

  if (state === "warmup") {
    return (
      <output className="state-toast state-toast--warmup">
        <span className="ic" aria-hidden="true">
          ↻
        </span>
        <span>
          slot <b>{t}</b> warming up — descargando daily / 1h / 15m desde TwelveData · señales del
          slot en pausa
        </span>
      </output>
    );
  }
  if (state === "degraded") {
    return (
      <output className="state-toast state-toast--degraded">
        <span className="ic" aria-hidden="true">
          ⚠
        </span>
        <span>
          <b>{slot?.error_code ?? "ENG-060"}</b> · 3 fallos consecutivos de fetch en <b>{t}</b> —
          revisar Dashboard → Motores
        </span>
      </output>
    );
  }
  if (state === "splus") {
    return (
      <output className="state-toast state-toast--splus">
        <span className="ic" aria-hidden="true">
          ★
        </span>
        <span>
          señal <b>S+</b> emitida en <b>{t}</b>
          {splusTime ? ` @ ${splusTime}` : ""}
        </span>
      </output>
    );
  }
  if (state === "error") {
    return (
      <output className="state-toast state-toast--error">
        <span className="ic" aria-hidden="true">
          ✕
        </span>
        <span>
          <b>{errCode ?? "ENG-001"}</b> · Data Engine caído · scan detenido — revisar Dashboard →
          Motores
        </span>
      </output>
    );
  }
  if (state === "scanning") {
    return (
      <output className="state-toast state-toast--scanning">
        <span className="ic" aria-hidden="true">
          ⟳
        </span>
        <span>
          escaneando <b>{t}</b> — fetch + scoring en curso
        </span>
      </output>
    );
  }
  if (state === "loading") {
    return (
      <output className="state-toast state-toast--loading">
        <span className="ic" aria-hidden="true">
          ◌
        </span>
        <span>cargando estado del backend…</span>
      </output>
    );
  }
  return null;
}
