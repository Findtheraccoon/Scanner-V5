import type { SignalPayload } from "@/api/types";
import { create } from "zustand";

interface SignalsState {
  /* Última señal por slot (mapeada por slot_id). El Cockpit Panel lee la
     señal del slot seleccionado de aquí. */
  bySlot: Record<number, SignalPayload>;
  /* Última señal global (independiente del slot) — útil para el state-toast
     "splus" que se dispara con cualquier S+ entrante. */
  latest: SignalPayload | null;

  applySignal: (signal: SignalPayload) => void;
  setBatch: (signals: SignalPayload[]) => void;
}

export const useSignalsStore = create<SignalsState>((set) => ({
  bySlot: {},
  latest: null,
  applySignal: (sig) =>
    set((s) => ({
      bySlot:
        sig.slot_id !== null && sig.slot_id !== undefined
          ? { ...s.bySlot, [sig.slot_id]: sig }
          : s.bySlot,
      latest: sig,
    })),
  setBatch: (signals) =>
    set(() => {
      const bySlot: Record<number, SignalPayload> = {};
      let latest: SignalPayload | null = null;
      for (const sig of signals) {
        if (sig.slot_id !== null && sig.slot_id !== undefined) {
          bySlot[sig.slot_id] = sig;
        }
        if (!latest || sig.computed_at > latest.computed_at) latest = sig;
      }
      return { bySlot, latest };
    }),
}));
