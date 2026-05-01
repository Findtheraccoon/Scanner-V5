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

interface FixtureSelectItem {
  /* `path` es el value del <option> y se manda como `fixture` al PATCH
     (BUG-010: el backend espera path relativo, no fixture_id). */
  path: string;
  /* `id` se muestra como label y matchea slot.fixture_id para preselección. */
  id: string;
  version?: string;
  compatible: boolean;
}

interface SlotCardProps {
  slot: SlotInfo;
  fixtures: FixtureSelectItem[];
}

/* UX-002 + BUG-003: cada slot es una tarjeta individual con flujo
   "ticker → fixture → toggle enable".

   Ticker y fixture son state LOCAL (drafts) hasta que el usuario
   activa el toggle. Antes los hacíamos commit-on-blur, pero el
   backend `disable_slot` wipea ticker+fixture al recibir
   `enabled: false`, así que cada autosave borraba lo recién tipeado
   y dejaba el select de fixture permanentemente disabled. Ahora:
   - drafts viven en local state hasta que enable=true.
   - re-sync con el slot del backend cuando llega data fresca (ej.
     tras un PATCH exitoso).
   - toggle ON valida ticker + fixture y manda un único PATCH con
     todo. Toggle OFF dispara disable_slot (wipea, igual que antes).
*/
function SlotCard({ slot, fixtures }: SlotCardProps): ReactElement {
  const patch = usePatchSlot();
  const { push: toast } = useToast();

  const [tickerDraft, setTickerDraft] = useState(slot.ticker ?? "");
  // BUG-010: el draft del fixture es el PATH relativo (lo que el backend
  // espera en `fixture`), no el fixture_id. Usamos slot.fixture_path
  // como source-of-truth para preselección.
  const [fixtureDraft, setFixtureDraft] = useState(slot.fixture_path ?? "");

  // Re-sync cuando el slot cambia desde el backend (refetch tras PATCH).
  useEffect(() => {
    setTickerDraft(slot.ticker ?? "");
    setFixtureDraft(slot.fixture_path ?? "");
  }, [slot.ticker, slot.fixture_path]);

  const errMsg = (e: unknown): string => {
    const err = e as ApiError;
    return typeof err.body === "string"
      ? err.body
      : err.body
        ? JSON.stringify(err.body)
        : err.message;
  };

  const onToggle = async (enabled: boolean) => {
    if (enabled) {
      const ticker = tickerDraft.trim().toUpperCase();
      if (!ticker) {
        toast(`slot ${slot.slot_id}: ingresá un ticker`, "warn");
        return;
      }
      if (!fixtureDraft) {
        toast(`slot ${slot.slot_id}: elegí un fixture`, "warn");
        return;
      }
      try {
        await patch.mutateAsync({
          slotId: slot.slot_id,
          body: { enabled: true, ticker, fixture: fixtureDraft },
        });
        toast(`slot ${slot.slot_id} (${ticker}) habilitado · warming up`, "success");
      } catch (e) {
        toast(`slot ${slot.slot_id}: ${errMsg(e)}`, "error");
      }
      return;
    }
    // enabled = false → disable_slot wipea ticker + fixture en el backend.
    try {
      await patch.mutateAsync({
        slotId: slot.slot_id,
        body: { enabled: false },
      });
      toast(`slot ${slot.slot_id} deshabilitado`, "info");
    } catch (e) {
      toast(`slot ${slot.slot_id}: ${errMsg(e)}`, "error");
    }
  };

  const stateClass = statusToState(slot.status);
  const cardClass = slot.enabled ? "slot-card" : "slot-card is-disabled";
  const slotIdStr = String(slot.slot_id).padStart(2, "0");
  // Editing está bloqueado mientras hay PATCH activo o el slot ya
  // está habilitado (cambios in-flight requieren disable + re-enable).
  const editingDisabled = patch.isPending || slot.enabled;

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
          disabled={editingDisabled}
        />
      </div>

      <div className="field">
        <label htmlFor={`fixture-${slot.slot_id}`}>fixture</label>
        <select
          id={`fixture-${slot.slot_id}`}
          className="inp"
          value={fixtureDraft}
          onChange={(e) => setFixtureDraft(e.target.value)}
          disabled={editingDisabled}
        >
          <option value="">
            {fixtures.length === 0 ? "— subí un fixture abajo —" : "— elegir —"}
          </option>
          {fixtures.map((f) => (
            <option key={f.path} value={f.path} disabled={!f.compatible}>
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
  const fixturesForSelect: FixtureSelectItem[] = fixtureList
    .filter((f) => f.fixture_id !== undefined && f.path !== undefined)
    .map((f) => ({
      // BUG-010: el value del <option> es el path relativo. El path
      // viene como absoluto/relativo según OS — el backend lo resuelve
      // contra fixtures_root, así que sirve cualquiera de los dos.
      path: f.path as string,
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
