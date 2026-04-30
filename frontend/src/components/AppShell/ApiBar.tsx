import {
  useAutoScanPause,
  useAutoScanResume,
  useAutoScanStatus,
  useScanManual,
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
  const scanMut = useScanManual();

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

  const handleScan = async () => {
    setPulseScan(true);
    if (wsState !== "connected") {
      // Sin token o backend caído — solo feedback visual local.
      toast.push("scan local — backend no conectado", "warn");
      return;
    }
    // El endpoint requiere body completo (ticker + fixture + candles).
    // Sin esos inputs es esperable que el backend devuelva 422; el botón
    // del Cockpit es realmente útil cuando hay slot seleccionado y
    // fixture cargada — por ahora lanzamos un dry-run y reportamos.
    try {
      await scanMut.mutateAsync({ slotId: selectedSlotId });
      toast.push("scan disparado", "success");
    } catch (e) {
      const status = (e as { status?: number }).status;
      if (status === 422) toast.push("scan manual requiere body completo", "warn");
      else toast.push("error al disparar el scan", "error");
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
