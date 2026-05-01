import type { ApiError } from "@/api/client";
import {
  useAutoScanPause,
  useAutoScanResume,
  useAutoScanStatus,
  useScanSlot,
} from "@/api/queries";
import { useToast } from "@/components/Toast/ToastProvider";
import { useApiUsageStore } from "@/stores/apiUsage";
import { useEngineStore } from "@/stores/engine";
import { useSlotsStore } from "@/stores/slots";
import { useEffect, useMemo, useState } from "react";

interface KeyDisplay {
  name: string;
  lastSeen: string;
  used: number;
  capacity: number;
  usedDaily: number;
  capacityDaily: number;
}

const PLACEHOLDER_KEYS: KeyDisplay[] = [
  { name: "key 1", lastSeen: "—", used: 0, capacity: 8, usedDaily: 0, capacityDaily: 800 },
  { name: "key 2", lastSeen: "—", used: 0, capacity: 8, usedDaily: 0, capacityDaily: 800 },
  { name: "key 3", lastSeen: "—", used: 0, capacity: 8, usedDaily: 0, capacityDaily: 800 },
  { name: "key 4", lastSeen: "—", used: 0, capacity: 8, usedDaily: 0, capacityDaily: 800 },
  { name: "key 5", lastSeen: "—", used: 0, capacity: 8, usedDaily: 0, capacityDaily: 800 },
];

function formatRelative(iso: string | null): string {
  if (!iso) return "—";
  const ms = Date.now() - new Date(iso).getTime();
  if (ms < 1500) return "ahora";
  if (ms < 60_000) return `hace ${Math.floor(ms / 1000)}s`;
  if (ms < 3_600_000) return `hace ${Math.floor(ms / 60_000)}m`;
  return `hace ${Math.floor(ms / 3_600_000)}h`;
}

export function ApiBar() {
  const toast = useToast();
  const wsState = useEngineStore((s) => s.ws);
  const keys = useApiUsageStore((s) => s.keys);

  const displayKeys = useMemo<KeyDisplay[]>(() => {
    const wsKeys = Object.values(keys);
    if (wsKeys.length === 0) return PLACEHOLDER_KEYS;
    return wsKeys.slice(0, 5).map((k) => ({
      name: k.key_id,
      lastSeen: formatRelative(k.last_call_ts),
      used: k.used_minute,
      capacity: k.max_minute,
      usedDaily: k.used_daily,
      capacityDaily: k.max_daily,
    }));
  }, [keys]);

  const autoStatus = useAutoScanStatus();
  const pauseMut = useAutoScanPause();
  const resumeMut = useAutoScanResume();
  const scanSlotMut = useScanSlot();

  const [pulseScan, setPulseScan] = useState(false);
  // Default OFF cuando no hay info confiable del backend (loading inicial,
  // sin token, backend caído). El toggle pasa a ON sólo cuando el backend
  // confirma `{paused: false}` — mostrar ON sin esa confirmación es
  // engañoso (el usuario asume que el auto-scan corre y puede no estarlo).
  const isAutoOn = autoStatus.data ? !autoStatus.data.paused : false;

  useEffect(() => {
    if (!pulseScan) return;
    const id = setTimeout(() => setPulseScan(false), 900);
    return () => clearTimeout(id);
  }, [pulseScan]);

  const handleAuto = async () => {
    try {
      if (isAutoOn) {
        await pauseMut.mutateAsync();
        toast.push("auto-scan pausado", "info");
      } else {
        await resumeMut.mutateAsync();
        toast.push("auto-scan reanudado", "success");
      }
    } catch (e) {
      const status = (e as { status?: number }).status;
      if (status === 503) toast.push("backend sin scan loop activo", "warn");
      else toast.push("error al cambiar el estado del auto-scan", "error");
    }
  };

  const selectedSlotId = useSlotsStore((s) => s.selectedSlotId);
  const allSlots = useSlotsStore((s) => s.slots);

  // BUG-019: el default selectedSlotId es 2 (legacy del Hi-Fi v2). Si
  // el usuario tiene solo slot 1 activo, click SCAN AHORA dispararía
  // sobre slot 2 (disabled) → 409. Resolvemos al primer slot operativo
  // del registry; si el seleccionado lo es, lo respetamos.
  const resolveScannableSlot = (): number | null => {
    const isScannable = (s: { status: string }): boolean =>
      s.status === "active" || s.status === "warming_up";
    if (selectedSlotId !== null) {
      const sel = allSlots.find((s) => s.slot_id === selectedSlotId);
      if (sel && isScannable(sel)) return selectedSlotId;
    }
    const first = allSlots.find(isScannable);
    return first ? first.slot_id : null;
  };

  const handleScan = async () => {
    setPulseScan(true);
    if (wsState !== "connected") {
      // Sin token o backend caído — solo feedback visual local.
      toast.push("scan local — backend no conectado", "warn");
      return;
    }
    // BUG-015 + BUG-019: el botón usa el endpoint /scan/slot/{id} y
    // resuelve sobre el primer slot operativo si el seleccionado no
    // está activo. Antes pegaba directo al selectedSlotId aunque fuera
    // disabled → 409 sistemático.
    const targetSlot = resolveScannableSlot();
    if (targetSlot === null) {
      toast.push(
        "no hay slots operativos · habilitá uno en Configuración Box 4",
        "warn",
      );
      return;
    }
    try {
      const result = await scanSlotMut.mutateAsync({ slotId: targetSlot });
      const tickerLabel = allSlots.find((s) => s.slot_id === targetSlot)?.ticker ?? "?";
      const r = result as {
        score?: number;
        conf?: string;
        signal?: boolean;
        dir?: string;
        fetch_meta?: {
          candles_daily_n: number;
          candles_1h_n: number;
          candles_15m_n: number;
        };
      };
      const fm = r.fetch_meta;
      const candlesPart = fm
        ? ` · ${fm.candles_daily_n}D/${fm.candles_1h_n}H/${fm.candles_15m_n}m`
        : "";
      const scorePart =
        r.score !== undefined && r.conf
          ? ` · ${r.conf} ${r.dir ?? ""} ${r.score.toFixed(1)}`
          : "";
      toast.push(
        `scan ${tickerLabel} (slot ${targetSlot})${scorePart}${candlesPart}`,
        "success",
      );
    } catch (e) {
      const err = e as ApiError;
      const detail =
        typeof err.body === "object" && err.body !== null && "detail" in err.body
          ? String((err.body as { detail: unknown }).detail)
          : err.message;
      if (err.status === 503) toast.push(`scan no disponible — ${detail}`, "warn");
      else if (err.status === 409) toast.push(`scan rechazado — ${detail}`, "warn");
      else if (err.status === 502)
        toast.push(`fetch falló — ${detail.slice(0, 80)}`, "error");
      else toast.push(`scan falló — ${detail.slice(0, 80)}`, "error");
    }
  };

  return (
    <section className="apibar" aria-label="estado api">
      <div className="apibar__cell apibar__cell--controls">
        <button
          type="button"
          className={pulseScan ? "btn-scan is-pulsing" : "btn-scan"}
          aria-label="ejecutar scan"
          onClick={handleScan}
        >
          <svg
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden="true"
          >
            <title>scan</title>
            <path d="M21 21l-4.35-4.35" />
            <circle cx="11" cy="11" r="7" />
          </svg>
          <span>{pulseScan ? "escaneando…" : "scan ahora"}</span>
        </button>
        <button
          type="button"
          className={isAutoOn ? "toggle is-on" : "toggle is-off"}
          aria-label="auto-scan toggle"
          aria-pressed={isAutoOn}
          onClick={handleAuto}
          disabled={pauseMut.isPending || resumeMut.isPending}
        >
          <span className="toggle__label">auto</span>
          <span className="toggle__switch" />
          <span className="toggle__state">{isAutoOn ? "on" : "off"}</span>
        </button>
      </div>

      {displayKeys.map((k) => (
        <div className="apibar__cell" key={k.name}>
          <div className="apibar__keyhead">
            <span className="apibar__keyname">{k.name}</span>
            <span className="apibar__keysep">·</span>
            <span className="apibar__keylast">{k.lastSeen}</span>
          </div>
          <div className="apibar__keyusage">
            {k.used}/{k.capacity}
          </div>
          <div className="apibar__bar">
            <i style={{ width: `${(k.used / Math.max(1, k.capacity)) * 100}%` }} />
          </div>
        </div>
      ))}

      <div className="apibar__cell">
        <div className="daily-stack">
          {displayKeys.map((row) => (
            <div className="daily-row" key={`d-${row.name}`}>
              <span className="daily-row__name">{row.name}</span>
              <span className="daily-row__bar">
                <i
                  style={{
                    width: `${(row.usedDaily / Math.max(1, row.capacityDaily)) * 100}%`,
                  }}
                />
              </span>
              <span className="daily-row__num">
                {row.usedDaily}
                <span className="dim">/{row.capacityDaily}</span>
              </span>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
