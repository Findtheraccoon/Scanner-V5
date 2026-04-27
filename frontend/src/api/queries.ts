import { useAuthStore } from "@/stores/auth";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./client";
import type {
  AutoScanStatus,
  EngineHealth,
  ScanManualResponse,
  SignalPayload,
  SlotInfo,
} from "./types";

const enabled = () => useAuthStore.getState().token !== null;

/* Health del motor — sirve de estado inicial del store engine antes de
   que llegue el primer `engine.status` por WS. Se refresca en background
   cada 30s para que el dashboard muestre uptime fresco. */
export function useEngineHealth() {
  const token = useAuthStore((s) => s.token);
  return useQuery<EngineHealth>({
    queryKey: ["engine.health"],
    queryFn: () => api<EngineHealth>("/engine/health"),
    enabled: token !== null,
    refetchInterval: 30_000,
    staleTime: 10_000,
  });
}

/* Lista de slots — alimenta la watchlist del Cockpit. */
export function useSlots() {
  const token = useAuthStore((s) => s.token);
  return useQuery<SlotInfo[]>({
    queryKey: ["slots"],
    queryFn: () => api<SlotInfo[]>("/slots"),
    enabled: token !== null,
    staleTime: 60_000,
  });
}

/* Última señal por slot. Si el slot todavía no tiene señal, el endpoint
   devuelve 404 — se atrapa y se devuelve null. */
export function useLatestSignal(slotId: number | null) {
  const token = useAuthStore((s) => s.token);
  return useQuery<SignalPayload | null>({
    queryKey: ["signals.latest", slotId],
    queryFn: async () => {
      if (slotId === null) return null;
      try {
        return await api<SignalPayload>("/signals/latest", {
          query: { slot_id: slotId },
        });
      } catch (e) {
        const status = (e as { status?: number }).status;
        if (status === 404) return null;
        throw e;
      }
    },
    enabled: token !== null && slotId !== null,
    staleTime: 5_000,
  });
}

/* Status del auto-scan loop — `{paused: bool}`. Sincroniza el toggle AUTO
   al cargar la página. */
export function useAutoScanStatus() {
  const token = useAuthStore((s) => s.token);
  return useQuery<AutoScanStatus>({
    queryKey: ["scan.auto.status"],
    queryFn: () => api<AutoScanStatus>("/scan/auto/status"),
    enabled: token !== null,
    staleTime: 10_000,
  });
}

/* Mutations */

interface ScanManualVariables {
  body?: Record<string, unknown>;
  /* slot_id que se marca como "scanning" en useScanningStore mientras
     dura la mutation. Si no se pasa, no se trackea visualmente. */
  slotId?: number;
}

export function useScanManual() {
  return useMutation<ScanManualResponse, Error, ScanManualVariables>({
    mutationFn: ({ body }) =>
      api<ScanManualResponse>("/scan/manual", {
        method: "POST",
        body: JSON.stringify(body ?? {}),
      }),
    onMutate: async ({ slotId }) => {
      if (slotId !== undefined) {
        const { useScanningStore } = await import("@/stores/scanning");
        useScanningStore.getState().start(slotId);
      }
    },
    onSettled: async (_data, _err, { slotId }) => {
      if (slotId !== undefined) {
        const { useScanningStore } = await import("@/stores/scanning");
        useScanningStore.getState().finish(slotId);
      }
    },
  });
}

export function useAutoScanPause() {
  const qc = useQueryClient();
  return useMutation<AutoScanStatus, Error, void>({
    mutationFn: () => api<AutoScanStatus>("/scan/auto/pause", { method: "POST" }),
    onSuccess: (data) => {
      qc.setQueryData(["scan.auto.status"], data);
    },
  });
}

export function useAutoScanResume() {
  const qc = useQueryClient();
  return useMutation<AutoScanStatus, Error, void>({
    mutationFn: () => api<AutoScanStatus>("/scan/auto/resume", { method: "POST" }),
    onSuccess: (data) => {
      qc.setQueryData(["scan.auto.status"], data);
    },
  });
}

export { enabled };
