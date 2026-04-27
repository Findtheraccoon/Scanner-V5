/* Selector compartido del Cockpit — devuelve los datos del slot
   activo combinando backend + fallback hardcoded del Hi-Fi v2. Se usa
   tanto desde la Watchlist como desde el Panel/Banner para mantener una
   única fuente de verdad. */

import type { SignalConfidence, SignalDirection } from "@/api/types";
import { useSignalsStore } from "@/stores/signals";
import { useSlotsStore } from "@/stores/slots";
import { SLOTS as FALLBACK_SLOTS, type SlotData } from "./data";

export interface EffectiveSlot {
  slotId: number;
  ticker: string | null;
  band: SignalConfidence | null;
  direction: SignalDirection;
  score: number | null;
  fixtureId: string | null;
  status: "active" | "warming_up" | "degraded" | "disabled";
  errorCode?: string;
}

const STATIC_BANDS: Record<number, SignalConfidence | null> = {
  1: "A",
  2: "A+",
  3: "S",
  4: "B",
  5: "S+",
  6: null,
};

/* Resuelve el slot por id usando estos pasos en orden:
     1. Slot del backend (useSlotsStore) — fuente cuando hay datos vivos.
     2. Fallback del Hi-Fi v2 (frontend/src/pages/Cockpit/data.ts).
   Si llega una señal del backend para ese slot, sobreescribe band/dir/score. */
export function useEffectiveSlot(slotId: number): EffectiveSlot {
  const backendSlot = useSlotsStore((s) => s.slots.find((sl) => sl.slot_id === slotId));
  const signal = useSignalsStore((s) => s.bySlot[slotId]);
  const fallback = FALLBACK_SLOTS.find((s) => s.id === slotId) as SlotData | undefined;

  const ticker = backendSlot?.ticker ?? fallback?.ticker ?? null;
  const band: SignalConfidence | null =
    signal?.conf ??
    (fallback?.band as SignalConfidence | null | undefined) ??
    STATIC_BANDS[slotId] ??
    null;
  const direction: SignalDirection =
    signal?.dir ?? ((fallback?.direction as SignalDirection | undefined) || "CALL");
  const score = signal?.score ?? fallback?.score ?? null;
  const fixtureId = backendSlot?.fixture_id ?? null;
  const status = backendSlot?.status ?? "active";
  const errorCode = backendSlot?.error_code;

  return {
    slotId,
    ticker,
    band,
    direction,
    score,
    fixtureId,
    status,
    errorCode,
  };
}
