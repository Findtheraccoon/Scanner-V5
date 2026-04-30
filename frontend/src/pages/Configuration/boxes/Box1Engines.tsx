import type { ApiError } from "@/api/client";
import {
  useEngineHealth,
  useSlots,
  useSystemRestart,
  useSystemShutdown,
  useValidatorReportLatest,
} from "@/api/queries";
import type { EngineStatusLevel } from "@/api/types";
import { useToast } from "@/components/Toast/ToastProvider";
import { Pilot } from "@/components/ui/Pilot";
import { useEngineStore } from "@/stores/engine";
import type { ReactElement } from "react";
import { Box, type BoxState } from "../Box";

/* Box 1 — Motores del backend (observabilidad pura).

   5 cards alineadas al orden de dependencias del lifespan de FastAPI:
   database → data → slot_registry → scoring → validator. Cada card
   lee de:
   - useEngineHealth (REST snapshot al arrancar).
   - useEngineStore (estado vivo · alimentado por WS engine.status).
   - useSlots para el contador del Slot Registry.
   - useValidatorReportLatest para el último run del Validator.

   Estado global del box:
   - ok    si los 5 motores están green.
   - warn  si alguno está yellow / paused.
   - err   si alguno está red.
   - pend  si no hay datos todavía.
*/

function levelToState(level: EngineStatusLevel | undefined): BoxState {
  if (level === undefined) return "pend";
  if (level === "green") return "ok";
  if (level === "yellow" || level === "paused") return "warn";
  if (level === "red") return "err";
  return "pend";
}

function aggregateState(levels: (EngineStatusLevel | undefined)[]): BoxState {
  if (levels.some((l) => l === undefined)) return "pend";
  if (levels.some((l) => l === "red")) return "err";
  if (levels.some((l) => l === "yellow" || l === "paused")) return "warn";
  return "ok";
}

function formatRel(iso: string | undefined | null): string {
  if (!iso) return "—";
  const dt = new Date(iso).getTime();
  if (Number.isNaN(dt)) return "—";
  const sec = Math.max(0, Math.round((Date.now() - dt) / 1000));
  if (sec < 60) return `hace ${sec}s`;
  if (sec < 3600) return `hace ${Math.round(sec / 60)}m`;
  return `hace ${Math.round(sec / 3600)}h`;
}

interface EngCardProps {
  name: string;
  kind: string;
  state: BoxState;
  body: ReactElement | string;
  deps: string;
}

function EngCard({ name, kind, state, body, deps }: EngCardProps): ReactElement {
  const cls = state === "ok" ? "eng-card" : `eng-card is-${state}`;
  return (
    <div className={cls}>
      <div className="eng-card__head">
        <div>
          <div className="eng-card__name">{name}</div>
          <div className="eng-card__role">{kind}</div>
        </div>
        <Pilot state={state} />
      </div>
      <div className="eng-card__body">{body}</div>
      <div className="eng-card__deps">
        deps · <span className="ref">{deps}</span>
      </div>
    </div>
  );
}

export function Box1Engines(): ReactElement {
  const health = useEngineHealth();
  const slotsQuery = useSlots();
  const lastReport = useValidatorReportLatest();
  const dataPaused = useEngineStore((s) => s.dataPaused);
  const shutdown = useSystemShutdown();
  const restart = useSystemRestart();
  const { push: toast } = useToast();

  const errMsg = (e: unknown): string => {
    const err = e as ApiError;
    return typeof err.body === "string"
      ? err.body
      : err.body
        ? JSON.stringify(err.body)
        : err.message;
  };

  const onShutdown = async () => {
    if (
      !confirm(
        "¿detener el backend? Esto cierra todos los procesos asociados y la pestaña dejará de funcionar.",
      )
    )
      return;
    try {
      await shutdown.mutateAsync();
      toast("backend deteniéndose…", "warn");
    } catch (e) {
      toast(`shutdown falló — ${errMsg(e)}`, "error");
    }
  };

  const onRestart = async () => {
    if (
      !confirm("¿reiniciar el backend? El proceso se cerrará y volverá a arrancar (~3 segundos).")
    )
      return;
    try {
      await restart.mutateAsync();
      toast("backend reiniciándose…", "info");
    } catch (e) {
      toast(`restart falló — ${errMsg(e)}`, "error");
    }
  };

  const data = health.data;
  const slots = slotsQuery.data ?? [];
  const slotsActive = slots.filter((s) => s.status === "active").length;
  const slotsWarming = slots.filter((s) => s.status === "warming_up").length;
  const slotsDegraded = slots.filter((s) => s.status === "degraded").length;
  const slotsDisabled = slots.filter((s) => s.status === "disabled").length;

  const dbState = levelToState(data?.database.status);
  const dataState = levelToState(data?.data.status);
  const slotRegistryState = aggregateState(
    slots.length === 0
      ? [undefined]
      : slots.map((s) => (s.status === "degraded" ? "red" : "green")),
  );
  const scoringState = levelToState(data?.scoring.status);
  // El Validator no expone status global directo en /engine/health hoy;
  // tomamos el overall_status del último reporte como proxy.
  const validatorState: BoxState =
    lastReport.data === null || lastReport.data === undefined
      ? "pend"
      : lastReport.data.overall_status === "pass"
        ? "ok"
        : lastReport.data.overall_status === "warning"
          ? "warn"
          : "err";

  const overall = aggregateState([
    data?.database.status,
    data?.data.status,
    slots.length === 0 ? undefined : "green",
    data?.scoring.status,
    lastReport.data === undefined ? undefined : "green",
  ]);

  const total = 5;
  const okCount = [dbState, dataState, slotRegistryState, scoringState, validatorState].filter(
    (s) => s === "ok",
  ).length;

  return (
    <Box
      id={1}
      state={overall}
      title="Motores del backend"
      sub={
        <>
          5 motores arrancan con el lifespan FastAPI · esta vista es{" "}
          <span className="ref">sólo observabilidad</span> · no hay arranque manual desde la UI
        </>
      }
      statusText={`${okCount} / ${total} operativos`}
    >
      <div className="toolbar">
        <span className="toolbar__left">
          control del proceso del backend · usar con cuidado · cerrar la pestaña también detiene el
          backend tras 60s sin reconexión
        </span>
        <div className="toolbar__right">
          <button
            type="button"
            className="btn"
            onClick={onRestart}
            disabled={restart.isPending || shutdown.isPending}
          >
            {restart.isPending ? "reiniciando…" : "reiniciar backend"}
          </button>
          <button
            type="button"
            className="btn is-danger"
            onClick={onShutdown}
            disabled={shutdown.isPending || restart.isPending}
          >
            {shutdown.isPending ? "deteniendo…" : "detener backend"}
          </button>
        </div>
      </div>

      <div className="eng-cards">
        <EngCard
          name="database"
          kind="engine · persistencia"
          state={dbState}
          body={
            <>
              SQLite operativa + archive
              <br />
              heartbeat <span className="num">{formatRel(data?.last_heartbeat_at)}</span>
              {data?.database.message ? (
                <>
                  <br />
                  <span className="num">{data.database.message}</span>
                </>
              ) : null}
            </>
          }
          deps="—"
        />

        <EngCard
          name="data engine"
          kind="engine · provider + fetch"
          state={dataPaused ? "warn" : dataState}
          body={
            <>
              KeyPool round-robin
              <br />
              {dataPaused ? (
                <span className="num">auto-scan en pausa</span>
              ) : (
                <>
                  estado: <span className="num">{data?.data.status ?? "—"}</span>
                </>
              )}
              {data?.data.message ? (
                <>
                  <br />
                  <span className="num">{data.data.message}</span>
                </>
              ) : null}
            </>
          }
          deps="database"
        />

        <EngCard
          name="slot registry"
          kind="module · runtime registry"
          state={slotRegistryState}
          body={
            <>
              <span className="num">{slotsActive}</span> activos ·{" "}
              <span className="num">{slotsDisabled}</span> vacíos
              <br />
              <span className="num">{slotsWarming}</span> warming up
              <br />
              <span className="num">{slotsDegraded}</span> degraded
            </>
          }
          deps="database · data engine"
        />

        <EngCard
          name="scoring"
          kind="engine · análisis"
          state={scoringState}
          body={
            <>
              motor v5.2.0
              <br />
              healthcheck: <span className="num">{data?.scoring.status ?? "—"}</span>
              {data?.scoring.error_code ? (
                <>
                  <br />
                  <span className="num">{data.scoring.error_code}</span>
                </>
              ) : null}
            </>
          }
          deps="slot registry"
        />

        <EngCard
          name="validator"
          kind="module · diagnóstico A–G"
          state={validatorState}
          body={
            lastReport.data ? (
              <>
                último run · {formatRel(lastReport.data.finished_at)}
                <br />
                trigger · <span className="num">{lastReport.data.trigger}</span>
                <br />
                <span className="num">{lastReport.data.overall_status}</span> ·{" "}
                <span className="num">{lastReport.data.tests.length}</span> tests
              </>
            ) : (
              "sin reportes todavía"
            )
          }
          deps="scoring"
        />
      </div>

      <div className="eng-flow">
        <span className="eng-flow__lbl">flujo de arranque · lifespan FastAPI</span>
        <span className="eng-flow__node">database</span>
        <span className="eng-flow__arr">→</span>
        <span className="eng-flow__node">data engine</span>
        <span className="eng-flow__arr">→</span>
        <span className="eng-flow__node">slot registry</span>
        <span className="eng-flow__arr">→</span>
        <span className="eng-flow__node">scoring</span>
        <span className="eng-flow__arr">→</span>
        <span className="eng-flow__node">validator</span>
      </div>

      <div className="note">
        cards leen <span className="accent">/api/v1/engine/health</span> + WS{" "}
        <span className="accent">engine.status</span> · si un motor cae, su card se pone amarilla /
        roja y el dot del rail también — sin acción manual desde acá
      </div>
    </Box>
  );
}
