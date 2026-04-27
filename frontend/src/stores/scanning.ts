import { create } from "zustand";

/* Estado efímero de scans en curso. El botón "scan ahora" agrega el
   slot a `active` antes de la llamada y lo limpia al terminar (success
   o error). El loop AUTO emite via WS, donde el listener también puede
   marcar/limpiar slots según evento. La UI usa este flag para:
     · pulse visual en la card de la watchlist
     · ring sutil alrededor del banner del Cockpit
   No se persiste — se pierde al recargar la página. */

interface ScanningState {
  active: Set<number>;
  start: (slotId: number) => void;
  finish: (slotId: number) => void;
  reset: () => void;
  isScanning: (slotId: number) => boolean;
}

export const useScanningStore = create<ScanningState>((set, get) => ({
  active: new Set<number>(),
  start: (slotId) =>
    set((s) => {
      const next = new Set(s.active);
      next.add(slotId);
      return { active: next };
    }),
  finish: (slotId) =>
    set((s) => {
      if (!s.active.has(slotId)) return {};
      const next = new Set(s.active);
      next.delete(slotId);
      return { active: next };
    }),
  reset: () => set({ active: new Set() }),
  isScanning: (slotId) => get().active.has(slotId),
}));
