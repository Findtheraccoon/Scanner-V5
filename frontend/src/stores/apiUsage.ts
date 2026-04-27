import type { ApiUsageTickPayload, KeyUsage } from "@/api/types";
import { create } from "zustand";

interface ApiUsageState {
  keys: Record<string, KeyUsage>;
  applyTick: (payload: ApiUsageTickPayload) => void;
  setKeys: (keys: KeyUsage[]) => void;
}

export const useApiUsageStore = create<ApiUsageState>((set) => ({
  keys: {},
  applyTick: (p) =>
    set((s) => ({
      keys: { ...s.keys, [p.key_id]: p },
    })),
  setKeys: (keys) =>
    set({
      keys: Object.fromEntries(keys.map((k) => [k.key_id, k])),
    }),
}));
