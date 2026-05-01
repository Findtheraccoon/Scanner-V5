import type { ApiError } from "@/api/client";
import {
  useDeleteFixture,
  useFixtures,
  usePatchSlot,
  useSlots,
  useUploadFixture,
} from "@/api/queries";
import type { SlotInfo, SlotRuntimeStatus } from "@/api/types";
import { useToast } from "@/components/Toast/ToastProvider";
import { Dropzone } from "@/components/ui/Dropzone";
import { Pilot } from "@/components/ui/Pilot";
import { Toggle } from "@/components/ui/Toggle";
import { type ReactElement, useEffect, useState } from "react";
import { Box, type BoxState } from "../Box";

/* Box 4 — Slot Registry + fixtures.

   Sub-secciones:
   - Tabla de los 6 slots fijos con ticker · fixture (select) · toggle
     enable/disable · runtime status (active/warming/degraded/disabled).
   - Biblioteca de fixtures · lista los .json del backend con metadata
     + sha256 + engine_compatibility + slots que lo usan + delete.
   - Upload · dropzone para subir fixtures nuevos. */

function statusToState(st: SlotRuntimeStatus): BoxState {
  if (st === "active") return "ok";
  if (st === "warming_up") return "warn";
  if (st === "degraded") return "err";
  return "pend";
}

function statusLabel(st: SlotRuntimeStatus): string {
  if (st === "active") return "active";
  if (st === "warming_up") return "warming up";
  if (st === "degraded") return "degraded";
  return "disabled";
}

function aggregateSlotsState(slots: SlotInfo[]): BoxState {
  // Semáforo (UX-001):
  // - rojo si NO hay slots habilitados (todos disabled o lista vacía).
  // - rojo si todos los habilitados están degraded.
  // - warn si algún slot warming o degraded pero hay activos.
  // - verde si al menos 1 active y ningún degraded.
  if (slots.length === 0) return "err";
  const enabled = slots.filter((s) => s.status !== "disabled");
  if (enabled.length === 0) return "err"; // todos disabled = no configurado
  const allDegraded = enabled.every((s) => s.status === "degraded");
  if (allDegraded) return "err";
  const someWarming = enabled.some((s) => s.status === "warming_up");
  const someDegraded = enabled.some((s) => s.status === "degraded");
  if (someWarming || someDegraded) return "warn";
  return "ok";
}

interface SlotCardProps {
  slot: SlotInfo;
  fixtures: { id: string; version?: string; compatible: boolean }[];
}

/* UX-002: cada slot es una tarjeta individual con flujo
   "ticker → fixture → toggle enable" en lugar de fila de tabla.
   El ticker es editable inline (commit on blur o Enter); el fixture
   es un select; el toggle dispara PATCH con validación. */
function SlotCard({ slot, fixtures }: SlotCardProps): ReactElement {
  const patch = usePatchSlot();
  const { push: toast } = useToast();

  // Estado local del ticker — input editable; commit on blur o Enter.
  const [tickerDraft, setTickerDraft] = useState(slot.ticker ?? "");
  // Re-sync cuando el slot cambia desde el backend (ej. tras PATCH).
  useEffect(() => {
    setTickerDraft(slot.ticker ?? "");
  }, [slot.ticker]);

  const errMsg = (e: unknown): string => {
    const err = e as ApiError;
    return typeof err.body === "string"
      ? err.body
      : err.body
        ? JSON.stringify(err.body)
        : err.message;
  };

  const commitTicker = async () => {
    const next = tickerDraft.trim().toUpperCase();
    if (next === (slot.ticker ?? "")) return;
    if (!next) {
      // Borrar ticker → deshabilitar slot.
      try {
        await patch.mutateAsync({
          slotId: slot.slot_id,
          body: { enabled: false },
        });
        toast(`slot ${slot.slot_id}: ticker borrado · deshabilitado`, "info");
      } catch (e) {
        toast(`slot ${slot.slot_id}: ${errMsg(e)}`, "error");
        setTickerDraft(slot.ticker ?? "");
      }
      return;
    }
    // Si ya tenía fixture, mantener config con nuevo ticker; sino solo guardar
    // el ticker (el slot quedará pendiente de fixture).
    try {
      await patch.mutateAsync({
        slotId: slot.slot_id,
        body: {
          enabled: slot.enabled && !!slot.fixture_id,
          ticker: next,
          fixture: slot.fixture_id ?? "",
        },
      });
      toast(`slot ${slot.slot_id}: ticker → ${next}`, "success");
    } catch (e) {
      toast(`slot ${slot.slot_id}: ${errMsg(e)}`, "error");
      setTickerDraft(slot.ticker ?? "");
    }
  };

  const onChangeFixture = async (fid: string) => {
    if (!slot.ticker) {
      toast(`slot ${slot.slot_id}: ingresá ticker primero`, "warn");
      return;
    }
    try {
      await patch.mutateAsync({
        slotId: slot.slot_id,
        body: { enabled: slot.enabled, ticker: slot.ticker, fixture: fid },
      });
      toast(`slot ${slot.slot_id}: fixture → ${fid}`, "success");
    } catch (e) {
      toast(`slot ${slot.slot_id}: ${errMsg(e)}`, "error");
    }
  };

  const onToggle = async (enabled: boolean) => {
    if (enabled && (!slot.ticker || !slot.fixture_id)) {
      toast(`slot ${slot.slot_id}: completá ticker y fixture antes de habilitar`, "warn");
      return;
    }
    try {
      await patch.mutateAsync({
        slotId: slot.slot_id,
        body: enabled
          ? { enabled: true, ticker: slot.ticker ?? "", fixture: slot.fixture_id ?? "" }
          : { enabled: false },
      });
      toast(`slot ${slot.slot_id} ${enabled ? "habilitado" : "deshabilitado"}`, "info");
    } catch (e) {
      toast(`slot ${slot.slot_id}: ${errMsg(e)}`, "error");
    }
  };

  const stateClass = statusToState(slot.status);
  const cardClass = slot.enabled ? "slot-card" : "slot-card is-disabled";
  const slotIdStr = String(slot.slot_id).padStart(2, "0");

  return (
    <div className={cardClass}>
      <div className="slot-card__head">
        <span className="slot-card__id">slot {slotIdStr}</span>
        <span className={`runtime-status${stateClass !== "ok" ? ` is-${stateClass}` : ""}`}>
          <Pilot state={stateClass} />
          {statusLabel(slot.status)}
          {slot.error_code ? <span className="num"> · {slot.error_code}</span> : null}
        </span>
      </div>

      <div className="field">
        <label htmlFor={`ticker-${slot.slot_id}`}>ticker</label>
        <input
          id={`ticker-${slot.slot_id}`}
          className="inp"
          type="text"
          value={tickerDraft}
          placeholder="ej. SPY"
          maxLength={10}
          onChange={(e) => setTickerDraft(e.target.value)}
          onBlur={commitTicker}
          onKeyDown={(e) => {
            if (e.key === "Enter") (e.target as HTMLInputElement).blur();
          }}
          disabled={patch.isPending}
        />
      </div>

      <div className="field">
        <label htmlFor={`fixture-${slot.slot_id}`}>fixture</label>
        <select
          id={`fixture-${slot.slot_id}`}
          className="inp"
          value={slot.fixture_id ?? ""}
          onChange={(e) => onChangeFixture(e.target.value)}
          disabled={patch.isPending || !slot.ticker || fixtures.length === 0}
        >
          <option value="">— elegir —</option>
          {fixtures.map((f) => (
            <option key={f.id} value={f.id} disabled={!f.compatible}>
              {f.id} {f.version ? `· ${f.version}` : ""}
              {!f.compatible ? " · incompatible" : ""}
            </option>
          ))}
        </select>
      </div>

      <div className="slot-card__foot">
        <Toggle
          on={slot.enabled}
          onChange={onToggle}
          disabled={patch.isPending}
          ariaLabel={`enable slot ${slot.slot_id}`}
        />
      </div>
    </div>
  );
}

export function Box4Slots(): ReactElement {
  const slots = useSlots();
  const fixtures = useFixtures();
  const upload = useUploadFixture();
  const del = useDeleteFixture();
  const { push: toast } = useToast();

  const slotList = slots.data ?? [];
  const fixtureList = fixtures.data?.items ?? [];
  const fixturesForSelect = fixtureList
    .filter((f) => f.fixture_id !== undefined)
    .map((f) => ({
      id: f.fixture_id as string,
      version: f.fixture_version,
      compatible: f.engine_compatible !== false,
    }));

  // UX-002: siempre 6 tarjetas (slot 01–06). Cuando el backend devuelve
  // datos para un slot, los usamos; si el slot no existe todavía
  // (backend offline o nunca configurado) mostramos placeholder para
  // que el usuario pueda ingresar ticker + fixture directamente.
  const SLOT_IDS = [1, 2, 3, 4, 5, 6] as const;
  const placeholderSlot = (id: number): SlotInfo => ({
    slot_id: id,
    ticker: null,
    status: "disabled",
    fixture_id: null,
    enabled: false,
  });
  const slotsForRender: SlotInfo[] = SLOT_IDS.map(
    (id) => slotList.find((s) => s.slot_id === id) ?? placeholderSlot(id),
  );

  const counts = {
    active: slotList.filter((s) => s.status === "active").length,
    warming: slotList.filter((s) => s.status === "warming_up").length,
    degraded: slotList.filter((s) => s.status === "degraded").length,
    disabled: slotList.filter((s) => s.status === "disabled").length,
  };

  const state = aggregateSlotsState(slotList);
  const statusText =
    slotList.length === 0
      ? "—"
      : `${counts.active} activos · ${counts.warming} warming · ${counts.degraded} degraded`;

  const errMsg = (e: unknown): string => {
    const err = e as ApiError;
    return typeof err.body === "string"
      ? err.body
      : err.body
        ? JSON.stringify(err.body)
        : err.message;
  };

  const onUpload = async (file: File) => {
    try {
      const r = await upload.mutateAsync({ file });
      toast(`fixture subido: ${r.fixture_id}`, "success");
    } catch (e) {
      toast(`upload falló — ${errMsg(e)}`, "error");
    }
  };

  const onDelete = async (id: string) => {
    if (!confirm(`¿borrar fixture "${id}"? esta acción es irreversible.`)) return;
    try {
      await del.mutateAsync({ fixtureId: id });
      toast(`fixture eliminado: ${id}`, "info");
    } catch (e) {
      toast(`no se pudo eliminar — ${errMsg(e)}`, "error");
    }
  };

  return (
    <Box
      id={4}
      state={state}
      title="Slot Registry + fixtures"
      sub={
        <>
          6 slots fijos · enable/disable dispara warmup + revalidación A/B/C · benchmark lo define
          el fixture
        </>
      }
      statusText={statusText}
    >
      <div className="slot-cards">
        {slotsForRender.map((s) => (
          <SlotCard key={s.slot_id} slot={s} fixtures={fixturesForSelect} />
        ))}
      </div>

      {/* Biblioteca de fixtures */}
      <div className="lib-wrap">
        <div className="lib-head">
          <span>biblioteca de fixtures · {fixtures.data?.fixtures_dir ?? "—"}</span>
          <span className="count">
            {fixtureList.length === 0
              ? "vacía"
              : `${fixtureList.length} archivo${fixtureList.length === 1 ? "" : "s"}`}
          </span>
        </div>
        {fixtureList.length === 0 ? (
          <div style={{ padding: 16, textAlign: "center", color: "var(--t-55)" }}>
            {fixtures.isLoading ? "cargando…" : "no hay fixtures · subí uno abajo"}
          </div>
        ) : (
          fixtureList.map((f) => (
            <div key={f.path} className="lib-row">
              <span className="nm">{f.fixture_id ?? f.filename ?? "?"}</span>
              <span>{f.fixture_version ?? "—"}</span>
              <span className="bench">
                <span className="bench-lab">bench</span>
                {f.benchmark_default ?? "—"}
              </span>
              <span className="compat">{f.engine_compat_range ?? "—"}</span>
              <span className={`hash is-${f.sha256_status === "ok" ? "ok" : "bad"}`}>
                {f.sha256_status === "ok"
                  ? "✓ hash ok"
                  : f.sha256_status === "mismatch"
                    ? "✕ mismatch"
                    : "—"}
              </span>
              <span className="used">
                {f.used_by_slots && f.used_by_slots.length > 0
                  ? `slot${f.used_by_slots.length === 1 ? "" : "s"} ${f.used_by_slots.join(", ")}`
                  : "no usado"}
              </span>
              <span style={{ textAlign: "right" }}>
                <button
                  type="button"
                  className="btn is-ghost is-danger sm"
                  onClick={() => onDelete(f.fixture_id ?? "")}
                  disabled={
                    !f.fixture_id ||
                    (f.used_by_slots !== undefined && f.used_by_slots.length > 0) ||
                    del.isPending
                  }
                >
                  eliminar
                </button>
              </span>
            </div>
          ))
        )}
      </div>

      {/* Upload de fixture */}
      <div className="upload-wrap">
        <div className="upload-wrap__sticker">cargar fixture nuevo</div>
        <Dropzone
          onFile={onUpload}
          accept=".json,application/json"
          label={
            <>
              arrastrá un <span className="accent">.json</span> acá
            </>
          }
          sub="valida estructura Pydantic + SHA-256 + engine_compat_range"
        />
      </div>

      <div className="note" style={{ marginTop: "var(--gap-3)" }}>
        cambiar el fixture o el toggle dispara <span className="accent">PATCH /slots/{"{id}"}</span>{" "}
        · el backend lanza warmup + revalidación A/B/C en background · el dot del rail se pone
        amarillo durante el warmup
      </div>
    </Box>
  );
}
