import type { SlotInfo, SlotStatusPayload } from "@/api/types";
import { create } from "zustand";

interface SlotsState {
  /* Lista de los 6 slots del registry (alimentado por GET /slots y por
     eventos slot.status del WS). */
  slots: SlotInfo[];
  /* Slot seleccionado en el Cockpit. Default 2 (matchea el is-selected
     del Hi-Fi v2 — segundo slot resaltado). */
  selectedSlotId: number;

  setSlots: (slots: SlotInfo[]) => void;
  applySlotStatus: (payload: SlotStatusPayload) => void;
  selectSlot: (slotId: number) => void;
}

export const useSlotsStore = create<SlotsState>((set) => ({
  slots: [],
  selectedSlotId: 2,
  setSlots: (slots) => set({ slots }),
  applySlotStatus: (p) =>
    set((s) => ({
      slots: s.slots.map((slot) =>
        slot.slot_id === p.slot_id
          ? {
              ...slot,
              status: p.status,
              message: p.message,
              error_code: p.error_code,
            }
          : slot,
      ),
    })),
  selectSlot: (slotId) => set({ selectedSlotId: slotId }),
}));
