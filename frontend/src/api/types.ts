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
