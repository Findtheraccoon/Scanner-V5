import { create } from "zustand";

/* Estado UI de la pestaña Configuración. Por ahora sólo el collapse
   por box (los 6 arrancan colapsados según decisión de producto · el
   usuario expande lo que necesita). Vivido en memoria; al recargar
   vuelve al default. */

export type BoxId = 1 | 2 | 3 | 4 | 5 | 6;

interface ConfigUiState {
  collapsed: Record<BoxId, boolean>;
  toggle: (id: BoxId) => void;
  set: (id: BoxId, collapsed: boolean) => void;
  collapseAll: () => void;
  expandAll: () => void;
}

const ALL_COLLAPSED: Record<BoxId, boolean> = {
  1: true,
  2: true,
  3: true,
  4: true,
  5: true,
  6: true,
};

export const useConfigUiStore = create<ConfigUiState>((set) => ({
  collapsed: { ...ALL_COLLAPSED },
  toggle: (id) => set((s) => ({ collapsed: { ...s.collapsed, [id]: !s.collapsed[id] } })),
  set: (id, collapsed) => set((s) => ({ collapsed: { ...s.collapsed, [id]: collapsed } })),
  collapseAll: () => set({ collapsed: { ...ALL_COLLAPSED } }),
  expandAll: () =>
    set({
      collapsed: { 1: false, 2: false, 3: false, 4: false, 5: false, 6: false },
    }),
}));
