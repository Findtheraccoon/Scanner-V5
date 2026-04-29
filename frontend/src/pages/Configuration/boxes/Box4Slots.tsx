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
import type { ReactElement } from "react";
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
  if (slots.length === 0) return "pend";
  if (slots.some((s) => s.status === "degraded")) return "err";
  if (slots.some((s) => s.status === "warming_up")) return "warn";
  if (slots.every((s) => s.status === "disabled")) return "pend";
  return "ok";
}

interface SlotRowProps {
  slot: SlotInfo;
  fixtures: { id: string; version?: string; compatible: boolean }[];
}

function SlotRow({ slot, fixtures }: SlotRowProps): ReactElement {
  const patch = usePatchSlot();
  const { push: toast } = useToast();
  const errMsg = (e: unknown): string => {
    const err = e as ApiError;
    return typeof err.body === "string"
      ? err.body
      : err.body
        ? JSON.stringify(err.body)
        : err.message;
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

  const stateClass = statusToState(slot.status);
  const rowClass = slot.enabled ? "" : "is-disabled";

  return (
    <tr className={rowClass}>
      <td className="col-id">{String(slot.slot_id).padStart(2, "0")}</td>
      <td className="col-tk">
        <input
          className="inp"
          type="text"
          value={slot.ticker ?? ""}
          placeholder="—"
          aria-label={`ticker slot ${slot.slot_id}`}
          readOnly
        />
      </td>
      <td className="col-fix">
        <select
          className="inp"
          value={slot.fixture_id ?? ""}
          onChange={(e) => onChangeFixture(e.target.value)}
          disabled={patch.isPending || fixtures.length === 0}
          aria-label={`fixture slot ${slot.slot_id}`}
        >
          <option value="">— elegir —</option>
          {fixtures.map((f) => (
            <option key={f.id} value={f.id} disabled={!f.compatible}>
              {f.id} {f.version ? `· ${f.version}` : ""}
              {!f.compatible ? " · incompatible" : ""}
            </option>
          ))}
        </select>
      </td>
      <td className="col-en">
        <Toggle
          on={slot.enabled}
          onChange={onToggle}
          disabled={patch.isPending}
          ariaLabel={`enable slot ${slot.slot_id}`}
        />
      </td>
      <td className="col-st">
        <span className={`runtime-status${stateClass !== "ok" ? ` is-${stateClass}` : ""}`}>
          <Pilot state={stateClass} />
          {statusLabel(slot.status)}
          {slot.error_code ? <span className="num"> · {slot.error_code}</span> : null}
        </span>
      </td>
    </tr>
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
      <table className="slots-table">
        <thead>
          <tr>
            <th className="col-id">#</th>
            <th className="col-tk">ticker</th>
            <th className="col-fix">fixture</th>
            <th className="col-en">enabled</th>
            <th className="col-st">runtime</th>
          </tr>
        </thead>
        <tbody>
          {slotList.length === 0 ? (
            <tr>
              <td colSpan={5} style={{ textAlign: "center", color: "var(--t-55)", padding: 20 }}>
                {slots.isLoading ? "cargando slots…" : "sin slots configurados"}
              </td>
            </tr>
          ) : (
            slotList.map((s) => <SlotRow key={s.slot_id} slot={s} fixtures={fixturesForSelect} />)
          )}
        </tbody>
      </table>

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
