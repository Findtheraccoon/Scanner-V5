/* Selector compartido del Cockpit — devuelve los datos del slot
   activo combinando registry (slots) + última señal del slot.

   UX-003: este selector NO usa data fake del Hi-Fi v2. Si no hay
   datos del backend para el slot, ticker/band/dir/score son `null`
   y los componentes consumidores (Banner, StateToast, Watchlist)
   deciden cómo renderizar el estado vacío. */

import type { SignalConfidence, SignalDirection } from "@/api/types";
import { useSignalsStore } from "@/stores/signals";
import { useSlotsStore } from "@/stores/slots";

export interface EffectiveSlot {
  slotId: number;
  ticker: string | null;
  band: SignalConfidence | null;
  direction: SignalDirection | null;
  score: number | null;
  fixtureId: string | null;
  status: "active" | "warming_up" | "degraded" | "disabled";
  errorCode?: string;
}

export function useEffectiveSlot(slotId: number): EffectiveSlot {
  const backendSlot = useSlotsStore((s) => s.slots.find((sl) => sl.slot_id === slotId));
  const signal = useSignalsStore((s) => s.bySlot[slotId]);

  return {
    slotId,
    ticker: backendSlot?.ticker ?? null,
    band: signal?.conf ?? null,
    direction: signal?.dir ?? null,
    score: signal?.score ?? null,
    fixtureId: backendSlot?.fixture_id ?? null,
    status: backendSlot?.status ?? "disabled",
    errorCode: backendSlot?.error_code,
  };
}
