import { useAuthStore } from "@/stores/auth";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError, api } from "./client";
import type {
  AutoScanStatus,
  CandlesResponse,
  ConfigCurrentResponse,
  ConfigLastInfo,
  ConfigLoadResponse,
  ConfigPutS3Response,
  ConfigPutStartupFlagsResponse,
  ConfigPutTdKeysResponse,
  ConfigReloadPoliciesResponse,
  ConfigSaveResponse,
  DatabaseRotateAggressiveResponse,
  DatabaseRotateResponse,
  DatabaseStatsResponse,
  DatabaseVacuumResponse,
  EngineHealth,
  FixtureDeleteResponse,
  FixtureUploadResponse,
  FixturesListResponse,
  S3BackupResponse,
  S3Config,
  S3ListResponse,
  S3RestoreResponse,
  ScanManualResponse,
  SignalPayload,
  RawSlotInfo,
  SlotInfo,
  SlotPatchBody,
  SlotPatchResponse,
  StartupFlags,
  TDKeyConfig,
  ValidatorConnectivityResult,
  ValidatorReport,
  ValidatorReportsListResponse,
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

/* Adapter del shape crudo de `/api/v1/slots` al `SlotInfo` que consume
   la UI. El backend serializa `slot` (no `slot_id`), `base_state` (no
   `enabled`), e incluye `fixture_path` que la UI necesita para el PATCH.
   BUG-010/011/012: el código previo trataba el response como `SlotInfo`
   directo y todos los componentes veían `slot_id=undefined`,
   `enabled=undefined`, sin acceso a fixture_path. */
function adaptSlot(raw: RawSlotInfo): SlotInfo {
  return {
    slot_id: raw.slot,
    ticker: raw.ticker,
    status: raw.status,
    fixture_id: raw.fixture_id,
    fixture_path: raw.fixture_path,
    benchmark: raw.benchmark,
    enabled: raw.base_state !== "DISABLED",
    error_code: raw.error_code ?? undefined,
  };
}

/* Lista de slots — alimenta la watchlist del Cockpit. */
export function useSlots() {
  const token = useAuthStore((s) => s.token);
  return useQuery<SlotInfo[]>({
    queryKey: ["slots"],
    queryFn: async () => {
      const raw = await api<RawSlotInfo[]>("/slots");
      return raw.map(adaptSlot);
    },
    enabled: token !== null,
    staleTime: 60_000,
  });
}

/* Velas para chart del Cockpit. Trae las últimas N velas del timeframe
   especificado desde la DB del backend (transparent-reads sobre op +
   archive si está configurado). BUG-022: alimenta el sparkline OHLC. */
export function useCandles(
  ticker: string | null,
  tf: "daily" | "1h" | "15m" = "15m",
  n = 50,
) {
  const token = useAuthStore((s) => s.token);
  return useQuery<CandlesResponse | null>({
    queryKey: ["candles", ticker, tf, n],
    queryFn: async () => {
      if (!ticker) return null;
      try {
        return await api<CandlesResponse>(`/candles/${ticker}`, {
          query: { tf, n },
        });
      } catch (e) {
        const status = (e as { status?: number }).status;
        if (status === 404) return { ticker, tf, candles: [] };
        throw e;
      }
    },
    enabled: token !== null && ticker !== null,
    staleTime: 10_000,
  });
}

/* Última señal por slot. El endpoint backend `/signals/latest` devuelve
   list[dict] (array). Tomamos el primer elemento — ya viene ordenado
   por compute_timestamp DESC LIMIT 1. Si el slot todavía no tiene
   señales, devolvemos null.

   BUG-017: el código previo tipaba el response como `SignalPayload`
   (objeto) e hacía `applySignal(latestQuery.data)` con el array →
   `sig.slot_id` undefined → el store nunca se actualizaba → Banner
   se quedaba en "ESPERANDO SEÑAL" aunque hubiera signals reales en DB. */
export function useLatestSignal(slotId: number | null) {
  const token = useAuthStore((s) => s.token);
  return useQuery<SignalPayload | null>({
    queryKey: ["signals.latest", slotId],
    queryFn: async () => {
      if (slotId === null) return null;
      try {
        const items = await api<SignalPayload[]>("/signals/latest", {
          query: { slot_id: slotId },
        });
        return items.length > 0 ? items[0] : null;
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

/* BUG-015: scan one-shot de un slot operativo. El backend resuelve
   ticker + fixture + candles desde el registry y data_engine; el
   frontend solo manda el slot_id. Reemplaza el botón scan del Cockpit
   que antes pegaba /scan/manual con body vacío y siempre fallaba 422. */
export function useScanSlot() {
  const qc = useQueryClient();
  return useMutation<ScanManualResponse, ApiError, { slotId: number }>({
    mutationFn: ({ slotId }) =>
      api<ScanManualResponse>(`/scan/slot/${slotId}`, { method: "POST" }),
    onMutate: async ({ slotId }) => {
      const { useScanningStore } = await import("@/stores/scanning");
      useScanningStore.getState().start(slotId);
    },
    onSettled: async (_data, _err, { slotId }) => {
      const { useScanningStore } = await import("@/stores/scanning");
      useScanningStore.getState().finish(slotId);
      // Refresh de la última señal del slot — el backend la persistió.
      qc.invalidateQueries({ queryKey: ["signals.latest", slotId] });
      // BUG-030: el scan trae candles nuevas (el backend hace fetch_for_scan
      // que persiste 15m/1h/daily). El chart del Cockpit debe refrescar
      // — sino sigue mostrando las candles viejas hasta `staleTime` (10s)
      // o hasta el próximo refetch. Invalidamos toda la query family
      // `["candles", ...]` para que el ticker afectado refresque.
      qc.invalidateQueries({ queryKey: ["candles"] });
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

/* ════════════════════════════════════════════════════════════════════
   CONFIG — Box 2 + Box 3 + Box 6
   ════════════════════════════════════════════════════════════════════ */

export function useConfigCurrent(includeSecrets = false) {
  const token = useAuthStore((s) => s.token);
  return useQuery<ConfigCurrentResponse>({
    queryKey: ["config.current", includeSecrets],
    queryFn: () =>
      api<ConfigCurrentResponse>("/config/current", {
        query: { include_secrets: includeSecrets },
      }),
    enabled: token !== null,
    staleTime: 10_000,
  });
}

export function useConfigLast() {
  const token = useAuthStore((s) => s.token);
  return useQuery<ConfigLastInfo | null>({
    queryKey: ["config.last"],
    queryFn: () => api<ConfigLastInfo | null>("/config/last"),
    enabled: token !== null,
    staleTime: 30_000,
  });
}

export function useConfigLoad() {
  const qc = useQueryClient();
  return useMutation<ConfigLoadResponse, Error, { path: string }>({
    mutationFn: ({ path }) =>
      api<ConfigLoadResponse>("/config/load", {
        method: "POST",
        body: JSON.stringify({ path }),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["config.current"] });
      qc.invalidateQueries({ queryKey: ["config.last"] });
    },
  });
}

export function useConfigSave() {
  const qc = useQueryClient();
  return useMutation<ConfigSaveResponse, Error, { path?: string }>({
    mutationFn: ({ path }) =>
      api<ConfigSaveResponse>("/config/save", {
        method: "POST",
        body: JSON.stringify(path !== undefined ? { path } : {}),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["config.current"] });
      qc.invalidateQueries({ queryKey: ["config.last"] });
    },
  });
}

export function useConfigSaveAs() {
  const qc = useQueryClient();
  return useMutation<ConfigSaveResponse, Error, { path: string }>({
    mutationFn: ({ path }) =>
      api<ConfigSaveResponse>("/config/save_as", {
        method: "POST",
        body: JSON.stringify({ path }),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["config.current"] });
      qc.invalidateQueries({ queryKey: ["config.last"] });
    },
  });
}

export function useConfigClear() {
  const qc = useQueryClient();
  return useMutation<{ cleared: boolean }, Error, void>({
    mutationFn: () => api<{ cleared: boolean }>("/config/clear", { method: "POST" }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["config.current"] });
    },
  });
}

export function usePutTdKeys() {
  const qc = useQueryClient();
  return useMutation<ConfigPutTdKeysResponse, Error, { keys: TDKeyConfig[] }>({
    mutationFn: ({ keys }) =>
      api<ConfigPutTdKeysResponse>("/config/twelvedata_keys", {
        method: "PUT",
        body: JSON.stringify({ twelvedata_keys: keys }),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["config.current"] });
    },
  });
}

export function usePutS3() {
  const qc = useQueryClient();
  return useMutation<ConfigPutS3Response, Error, { s3: S3Config | null }>({
    mutationFn: ({ s3 }) =>
      api<ConfigPutS3Response>("/config/s3", {
        method: "PUT",
        body: JSON.stringify({ s3_config: s3 }),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["config.current"] });
    },
  });
}

export function usePutStartupFlags() {
  const qc = useQueryClient();
  return useMutation<ConfigPutStartupFlagsResponse, Error, { flags: StartupFlags }>({
    mutationFn: ({ flags }) =>
      api<ConfigPutStartupFlagsResponse>("/config/startup_flags", {
        method: "PUT",
        body: JSON.stringify({ startup_flags: flags }),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["config.current"] });
    },
  });
}

export function useReloadPolicies() {
  return useMutation<ConfigReloadPoliciesResponse, Error, void>({
    mutationFn: () =>
      api<ConfigReloadPoliciesResponse>("/config/reload-policies", { method: "POST" }),
  });
}

/* ════════════════════════════════════════════════════════════════════
   FIXTURES — Box 4 (biblioteca + upload + delete)
   ════════════════════════════════════════════════════════════════════ */

export function useFixtures() {
  const token = useAuthStore((s) => s.token);
  return useQuery<FixturesListResponse>({
    queryKey: ["fixtures.list"],
    queryFn: () => api<FixturesListResponse>("/fixtures"),
    enabled: token !== null,
    staleTime: 30_000,
  });
}

export function useUploadFixture() {
  const qc = useQueryClient();
  return useMutation<FixtureUploadResponse, ApiError, { file: File }>({
    mutationFn: async ({ file }) => {
      const form = new FormData();
      form.append("file", file);
      const token = useAuthStore.getState().token;
      const headers: Record<string, string> = {};
      if (token) headers.authorization = `Bearer ${token}`;
      const res = await fetch("/api/v1/fixtures/upload", {
        method: "POST",
        body: form,
        headers,
      });
      if (!res.ok) {
        let body: unknown = null;
        try {
          body = await res.json();
        } catch {
          body = await res.text().catch(() => null);
        }
        throw new ApiError(`HTTP ${res.status}`, res.status, body);
      }
      return (await res.json()) as FixtureUploadResponse;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["fixtures.list"] });
    },
  });
}

export function useDeleteFixture() {
  const qc = useQueryClient();
  return useMutation<FixtureDeleteResponse, ApiError, { fixtureId: string }>({
    mutationFn: ({ fixtureId }) =>
      api<FixtureDeleteResponse>(`/fixtures/${encodeURIComponent(fixtureId)}`, {
        method: "DELETE",
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["fixtures.list"] });
    },
  });
}

/* ════════════════════════════════════════════════════════════════════
   VALIDATOR — Box 5 (run + connectivity + reports)
   ════════════════════════════════════════════════════════════════════ */

export function useValidatorReportLatest() {
  const token = useAuthStore((s) => s.token);
  return useQuery<ValidatorReport | null>({
    queryKey: ["validator.report.latest"],
    queryFn: async () => {
      try {
        return await api<ValidatorReport>("/validator/reports/latest");
      } catch (e) {
        if ((e as ApiError).status === 404) return null;
        throw e;
      }
    },
    enabled: token !== null,
    staleTime: 30_000,
  });
}

export function useValidatorReports(limit = 20) {
  const token = useAuthStore((s) => s.token);
  return useQuery<ValidatorReportsListResponse>({
    queryKey: ["validator.reports", limit],
    queryFn: () =>
      api<ValidatorReportsListResponse>("/validator/reports", {
        query: { limit },
      }),
    enabled: token !== null,
    staleTime: 30_000,
  });
}

export function useValidatorRun() {
  const qc = useQueryClient();
  return useMutation<ValidatorReport, Error, void>({
    mutationFn: () => api<ValidatorReport>("/validator/run", { method: "POST" }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["validator.report.latest"] });
      qc.invalidateQueries({ queryKey: ["validator.reports"] });
    },
  });
}

export function useValidatorConnectivity() {
  const qc = useQueryClient();
  return useMutation<ValidatorConnectivityResult, Error, void>({
    mutationFn: () =>
      api<ValidatorConnectivityResult>("/validator/connectivity", { method: "POST" }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["validator.reports"] });
    },
  });
}

/* ════════════════════════════════════════════════════════════════════
   DATABASE — vacuum + rotate + stats
   ════════════════════════════════════════════════════════════════════ */

export function useDatabaseStats() {
  const token = useAuthStore((s) => s.token);
  return useQuery<DatabaseStatsResponse>({
    queryKey: ["database.stats"],
    queryFn: () => api<DatabaseStatsResponse>("/database/stats"),
    enabled: token !== null,
    staleTime: 15_000,
  });
}

export function useDatabaseVacuum() {
  const qc = useQueryClient();
  return useMutation<DatabaseVacuumResponse, ApiError, void>({
    mutationFn: () => api<DatabaseVacuumResponse>("/database/vacuum", { method: "POST" }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["database.stats"] });
    },
  });
}

export function useDatabaseRotate() {
  const qc = useQueryClient();
  return useMutation<DatabaseRotateResponse, Error, void>({
    mutationFn: () => api<DatabaseRotateResponse>("/database/rotate", { method: "POST" }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["database.stats"] });
    },
  });
}

export function useDatabaseRotateAggressive() {
  const qc = useQueryClient();
  return useMutation<DatabaseRotateAggressiveResponse, ApiError, void>({
    mutationFn: () =>
      api<DatabaseRotateAggressiveResponse>("/database/rotate/aggressive", {
        method: "POST",
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["database.stats"] });
    },
  });
}

/* ════════════════════════════════════════════════════════════════════
   S3 BACKUP — Box 6 (backup + restore + listado)
   Las credenciales viajan en el body por compat con el endpoint actual
   (deuda histórica). Cuando el frontend tenga `.config` con S3 cargado,
   este hook lo lee del store y lo pasa.
   ════════════════════════════════════════════════════════════════════ */

export function useS3Backup() {
  return useMutation<S3BackupResponse, ApiError, { s3: S3Config }>({
    mutationFn: ({ s3 }) =>
      api<S3BackupResponse>("/database/backup", {
        method: "POST",
        body: JSON.stringify({ s3 }),
      }),
  });
}

export function useS3Restore() {
  return useMutation<S3RestoreResponse, ApiError, { s3: S3Config; key: string }>({
    mutationFn: ({ s3, key }) =>
      api<S3RestoreResponse>("/database/restore", {
        method: "POST",
        body: JSON.stringify({ s3, key }),
      }),
  });
}

export function useS3List() {
  return useMutation<S3ListResponse, ApiError, { s3: S3Config }>({
    mutationFn: ({ s3 }) =>
      api<S3ListResponse>("/database/backups", {
        method: "POST",
        body: JSON.stringify({ s3 }),
      }),
  });
}

/* ════════════════════════════════════════════════════════════════════
   SLOTS PATCH — Box 4 (enable/disable + cambio de fixture/ticker)
   ════════════════════════════════════════════════════════════════════ */

export function usePatchSlot() {
  const qc = useQueryClient();
  return useMutation<SlotPatchResponse, ApiError, { slotId: number; body: SlotPatchBody }>({
    mutationFn: ({ slotId, body }) =>
      api<SlotPatchResponse>(`/slots/${slotId}`, {
        method: "PATCH",
        body: JSON.stringify(body),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["slots"] });
    },
  });
}

/* ════════════════════════════════════════════════════════════════════
   SYSTEM — shutdown + restart (modo launcher · v1)
   ════════════════════════════════════════════════════════════════════ */

export function useSystemShutdown() {
  return useMutation<{ shutdown: boolean; message: string }, ApiError, void>({
    mutationFn: () =>
      api<{ shutdown: boolean; message: string }>("/system/shutdown", {
        method: "POST",
      }),
  });
}

export function useSystemRestart() {
  return useMutation<{ restart: boolean; flag_path: string; message: string }, ApiError, void>({
    mutationFn: () =>
      api<{ restart: boolean; flag_path: string; message: string }>("/system/restart", {
        method: "POST",
      }),
  });
}

export { enabled };
