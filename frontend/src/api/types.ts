/* Tipos del backend Scanner V5. Mantener en sync con
   `backend/api/routes/*.py` y `backend/modules/db/models.py`. */

export type EngineStatusLevel = "green" | "yellow" | "red" | "paused";
export type SlotRuntimeStatus = "active" | "warming_up" | "degraded" | "disabled";
export type SignalConfidence = "REVISAR" | "B" | "A" | "A+" | "S" | "S+";
export type SignalDirection = "CALL" | "PUT";
export type SignalLabel = "SETUP" | "REVISAR" | "NEUTRAL";

export interface EngineHealth {
  status: EngineStatusLevel;
  scoring: { status: EngineStatusLevel; message?: string; error_code?: string };
  data: { status: EngineStatusLevel; message?: string };
  database: { status: EngineStatusLevel; message?: string };
  uptime_seconds?: number;
  last_heartbeat_at?: string;
}

export interface SlotInfo {
  slot_id: number;
  ticker: string | null;
  status: SlotRuntimeStatus;
  fixture_id?: string | null;
  benchmark?: string | null;
  enabled: boolean;
  message?: string;
  error_code?: string;
}

export interface KeyUsage {
  key_id: string;
  used_minute: number;
  max_minute: number;
  used_daily: number;
  max_daily: number;
  last_call_ts: string | null;
  exhausted: boolean;
}

export interface SignalPayload {
  id: number;
  slot_id: number | null;
  ticker: string;
  conf: SignalConfidence;
  signal: SignalLabel;
  dir: SignalDirection | null;
  score: number;
  candle_timestamp: string;
  computed_at: string;
  fixture_id: string;
  engine_version: string;
  patterns?: Array<{ name: string; cat: string; sg: string; tf: string; w: number }>;
  layers?: Record<string, unknown>;
  chat_format?: string;
  snapshot_b64?: string;
}

export interface AutoScanStatus {
  paused: boolean;
}

export interface ScanManualResponse {
  id: number | null;
  conf: SignalConfidence;
  signal: SignalLabel;
  dir: SignalDirection | null;
  score: number;
  ticker: string;
  slot_id?: number | null;
  candle_timestamp: string;
  chat_format?: string;
}

/* WebSocket envelopes — `{event, payload}` */

export type WsEvent =
  | "signal.new"
  | "slot.status"
  | "engine.status"
  | "api_usage.tick"
  | "validator.progress"
  | "system.log";

export interface WsEnvelope<T = unknown> {
  event: WsEvent;
  payload: T;
  ts?: string;
}

export interface SlotStatusPayload {
  slot_id: number;
  status: SlotRuntimeStatus;
  message?: string;
  error_code?: string;
}

export interface EngineStatusPayload {
  engine: "data" | "scoring" | "database" | "validator";
  status: EngineStatusLevel;
  message?: string;
  error_code?: string;
}

export interface ApiUsageTickPayload extends KeyUsage {}

export interface ValidatorProgressPayload {
  run_id: string;
  trigger: "startup" | "manual" | "hot_reload" | "connectivity";
  test: string;
  status: "running" | "passed" | "warning" | "failed";
  message?: string;
}

export interface SystemLogPayload {
  level: "info" | "warning" | "error";
  message: string;
  source?: string;
}

/* ════════════════════════════════════════════════════════════════════
   CONFIGURACIÓN — UserConfig + endpoints `/api/v1/config/*`
   Espejo de `backend/modules/config/models.py`. El `.config` es un
   archivo portable plaintext; sin .config cargado el sistema arranca
   de cero (UserConfig vacío).
   ════════════════════════════════════════════════════════════════════ */

export interface TDKeyConfig {
  key_id: string;
  secret: string;
  credits_per_minute: number;
  credits_per_day: number;
  enabled: boolean;
}

export interface S3Config {
  endpoint_url: string | null;
  bucket: string;
  access_key_id: string;
  secret_access_key: string;
  region: string;
  key_prefix: string;
}

export interface StartupFlags {
  validator_run_at_startup: boolean;
  validator_parity_enabled: boolean;
  validator_parity_limit: number | null;
  heartbeat_interval_s: number;
  rotate_on_shutdown: boolean;
  aggressive_rotation_enabled: boolean;
  aggressive_rotation_interval_s: number;
  db_size_limit_mb: number;
}

export interface UserConfig {
  schema_version: string;
  name: string;
  twelvedata_keys: TDKeyConfig[];
  s3_config: S3Config | null;
  api_bearer_token: string | null;
  registry_path: string;
  preferences: Record<string, unknown>;
  auto_last_enabled: boolean;
  startup_flags: StartupFlags;
}

export interface ConfigCurrentResponse {
  loaded: boolean;
  config: UserConfig | null;
  path: string | null;
}

export interface ConfigLastInfo {
  path: string;
  loaded_at: string;
}

export interface ConfigLoadResponse {
  loaded: boolean;
  path: string;
  name: string;
  key_pool_reloaded: boolean;
}

export interface ConfigSaveResponse {
  saved: boolean;
  path: string;
}

export interface ConfigPutResponse {
  updated: boolean;
}

export interface ConfigPutTdKeysResponse extends ConfigPutResponse {
  count: number;
  key_pool_reloaded: boolean;
}

export interface ConfigPutS3Response extends ConfigPutResponse {
  configured: boolean;
}

export interface ConfigPutStartupFlagsResponse extends ConfigPutResponse {
  applied_immediately: string[];
  requires_restart: string[];
}

export interface ConfigReloadPoliciesResponse {
  applied: string[];
  reason?: string;
  current_db_size_limit_mb?: number;
}

/* ════════════════════════════════════════════════════════════════════
   FIXTURES — endpoints `/api/v1/fixtures/*`
   Espejo de `backend/modules/fixtures/models.py` + `api/routes/fixtures.py`.
   ════════════════════════════════════════════════════════════════════ */

export interface FixtureListItem {
  path: string;
  filename?: string;
  sha256?: string;
  sha256_status?: "ok" | "mismatch" | "no canonical";
  fixture_id?: string;
  fixture_version?: string;
  engine_compat_range?: string;
  ticker_default?: string;
  benchmark_default?: string | null;
  engine_compatible?: boolean;
  used_by_slots?: number[];
  error?: string;
}

export interface FixturesListResponse {
  fixtures_dir: string;
  items: FixtureListItem[];
  engine_version: string;
}

export interface FixtureUploadResponse {
  uploaded: boolean;
  fixture_id: string;
  fixture_version: string;
  ticker_default: string;
  sha256: string;
  json_path: string;
  sha256_path: string;
}

export interface FixtureDeleteResponse {
  deleted: boolean;
  fixture_id: string;
  paths: string[];
}

/* ════════════════════════════════════════════════════════════════════
   VALIDATOR — endpoints `/api/v1/validator/*`
   Espejo de `backend/modules/validator/models.py`.
   ════════════════════════════════════════════════════════════════════ */

export type ValidatorTrigger = "startup" | "manual" | "hot_reload" | "connectivity";
export type ValidatorOverallStatus = "pass" | "warning" | "fail";
export type ValidatorTestStatus = "passed" | "warning" | "failed" | "skipped" | "error";

export interface ValidatorTestResult {
  test_id: string;
  status: ValidatorTestStatus;
  message?: string;
  duration_ms?: number;
}

export interface ValidatorReport {
  run_id: string;
  trigger: ValidatorTrigger;
  started_at: string;
  finished_at: string;
  overall_status: ValidatorOverallStatus;
  tests: ValidatorTestResult[];
}

export interface ValidatorReportsListItem {
  run_id: string;
  trigger: ValidatorTrigger;
  started_at: string;
  finished_at: string;
  overall_status: ValidatorOverallStatus;
}

export interface ValidatorReportsListResponse {
  items: ValidatorReportsListItem[];
  next_cursor: string | null;
}

export interface ValidatorConnectivityResult {
  run_id: string;
  trigger: "connectivity";
  overall_status: ValidatorOverallStatus;
  td_keys: Array<{ key_id: string; ok: boolean; error?: string }>;
  s3?: { ok: boolean; error?: string } | null;
}

/* ════════════════════════════════════════════════════════════════════
   DATABASE — endpoints `/api/v1/database/*`
   ════════════════════════════════════════════════════════════════════ */

export interface DatabaseStatsTable {
  name: string;
  rows: number;
  retention_seconds: number | null;
  last_rotated_at?: string;
}

export interface DatabaseStatsResponse {
  archive_configured: boolean;
  tables: {
    operative: DatabaseStatsTable[];
    archive?: DatabaseStatsTable[];
  };
  size_mb_operative: number | null;
  size_limit_mb: number;
}

export interface DatabaseVacuumResponse {
  db_path: string;
  size_mb_before: number;
  size_mb_after: number;
}

export interface DatabaseRotateResponse {
  mode: "archive" | "delete_only";
  result: Record<string, unknown>;
}

export interface DatabaseRotateAggressiveResponse {
  triggered: boolean;
  size_mb_before: number;
  size_mb_after: number;
  rotation: Record<string, unknown> | null;
  vacuum_recommended: boolean;
}

/* ════════════════════════════════════════════════════════════════════
   S3 — endpoints `/api/v1/database/{backup,restore,backups}`
   ════════════════════════════════════════════════════════════════════ */

export interface S3BackupItem {
  key: string;
  size_bytes: number;
  last_modified: string;
}

export interface S3BackupResponse {
  key: string;
  size_bytes: number;
  etag?: string;
}

export interface S3ListResponse {
  bucket: string;
  key_prefix: string;
  objects: S3BackupItem[];
}

export interface S3RestoreResponse {
  sibling_path: string;
  size_bytes: number;
  notice: string;
}

/* ════════════════════════════════════════════════════════════════════
   SLOT PATCH (Box 4)
   ════════════════════════════════════════════════════════════════════ */

export interface SlotPatchBody {
  enabled: boolean;
  ticker?: string;
  fixture?: string;
  benchmark?: string | null;
}

export interface SlotPatchResponse {
  slot_id: number;
  status: SlotRuntimeStatus;
  message?: string;
}
