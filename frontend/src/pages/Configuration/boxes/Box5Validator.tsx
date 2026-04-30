import type { ApiError } from "@/api/client";
import {
  useValidatorConnectivity,
  useValidatorReportLatest,
  useValidatorReports,
  useValidatorRun,
} from "@/api/queries";
import type { EngineStatusLevel, ValidatorTestStatus } from "@/api/types";
import { useToast } from "@/components/Toast/ToastProvider";
import { Badge } from "@/components/ui/Badge";
import { Pilot, type PilotState } from "@/components/ui/Pilot";
import { useEngineStore } from "@/stores/engine";
import {
  type ValidatorTestRuntimeStatus,
  useValidatorProgressStore,
} from "@/stores/validatorProgress";
import type { ReactElement } from "react";
import { Box, type BoxState } from "../Box";

/* Box 5 — Validator + diagnóstico.

   Sub-secciones:
   - Grid 7 celdas (D · A · B · C · E · F · G) que se alimenta del
     store useValidatorProgressStore (WS validator.progress) durante
     un run, o del último reporte cuando no hay run en curso.
   - Histórico de reportes (cursor pagination · `useValidatorReports`).
   - Resumen compacto de motores (espejo del Box 1 sin el flow). */

const TEST_ORDER = ["D", "A", "B", "C", "E", "F", "G"] as const;
const TEST_LABELS: Record<(typeof TEST_ORDER)[number], string> = {
  D: "infra",
  A: "fixtures",
  B: "canonicals",
  C: "registry",
  E: "end-to-end",
  F: "parity",
  G: "conectividad",
};

function statusToCellState(
  st: ValidatorTestRuntimeStatus | ValidatorTestStatus | undefined,
): "ok" | "run" | "warn" | "fail" | "pend" {
  if (!st) return "pend";
  if (st === "passed") return "ok";
  if (st === "running") return "run";
  if (st === "warning") return "warn";
  if (st === "failed" || st === "error") return "fail";
  return "pend";
}

/* Semáforo (UX-001):
   - pend si nunca corrió (todas las celdas pend = sin reporte previo).
   - err  si alguna celda fail.
   - warn si alguna celda warn o running.
   - ok   si todas las celdas ok.
   - warn por default (mix de pend + ok = parcial, conservador). */
function aggregateState(cells: ("ok" | "run" | "warn" | "fail" | "pend")[]): BoxState {
  if (cells.every((c) => c === "pend")) return "pend";
  if (cells.some((c) => c === "fail")) return "err";
  if (cells.some((c) => c === "warn" || c === "run")) return "warn";
  if (cells.every((c) => c === "ok")) return "ok";
  return "warn";
}

export function Box5Validator(): ReactElement {
  const lastReport = useValidatorReportLatest();
  const reports = useValidatorReports(10);
  const run = useValidatorRun();
  const conn = useValidatorConnectivity();
  const progress = useValidatorProgressStore();
  const engineState = useEngineStore();
  const { push: toast } = useToast();

  const enginePilot = (level: EngineStatusLevel): PilotState => {
    if (level === "green") return "ok";
    if (level === "red") return "err";
    if (level === "offline") return "pend";
    return "warn";
  };

  const errMsg = (e: unknown): string => {
    const err = e as ApiError;
    return typeof err.body === "string"
      ? err.body
      : err.body
        ? JSON.stringify(err.body)
        : err.message;
  };

  const isRunning = progress.runId !== null && progress.finishedAt === null;

  // Resolución del grid: si hay un run en vivo, leemos del store.
  // Si no, leemos del último reporte (`tests` array). Si no hay tampoco,
  // todas las celdas son `pend`.
  const cellStates: Record<string, "ok" | "run" | "warn" | "fail" | "pend"> = {};
  for (const t of TEST_ORDER) {
    if (isRunning) {
      cellStates[t] = statusToCellState(progress.tests[t]);
    } else if (lastReport.data) {
      const tr = lastReport.data.tests.find(
        (x) => x.test_id === t || x.test_id.toUpperCase().startsWith(t),
      );
      cellStates[t] = statusToCellState(tr?.status);
    } else {
      cellStates[t] = "pend";
    }
  }

  const cellsArr = TEST_ORDER.map((t) => cellStates[t]);
  const completedTests = cellsArr.filter((s) => s === "ok" || s === "warn" || s === "fail").length;
  const overall = aggregateState(cellsArr);

  let progressPct: number;
  let barClass: string;
  let lblText: string;
  if (isRunning) {
    progressPct = (completedTests / 7) * 100;
    barClass = "is-warn";
    lblText = `${completedTests}/7 · ${Math.round(progressPct)}% · running`;
  } else if (lastReport.data) {
    progressPct = 100;
    if (lastReport.data.overall_status === "pass") {
      barClass = "is-ok";
    } else if (lastReport.data.overall_status === "warning") {
      barClass = "is-warn";
    } else {
      barClass = "is-warn";
    }
    const dur = Math.round(
      (new Date(lastReport.data.finished_at).getTime() -
        new Date(lastReport.data.started_at).getTime()) /
        1000,
    );
    lblText = `${lastReport.data.tests.length}/7 · ${lastReport.data.overall_status} · ${dur}s`;
  } else {
    progressPct = 0;
    barClass = "";
    lblText = "—";
  }

  const statusText = isRunning
    ? `corriendo · ${completedTests}/7`
    : lastReport.data
      ? `último · ${lastReport.data.overall_status} · ${lastReport.data.tests.length}/7`
      : "sin reportes";

  const onRun = async () => {
    progress.reset();
    try {
      const r = await run.mutateAsync();
      toast(
        `validator: ${r.overall_status} · ${r.tests.length}/7`,
        r.overall_status === "pass" ? "success" : "warn",
      );
    } catch (e) {
      toast(`validator falló — ${errMsg(e)}`, "error");
    }
  };

  const onConnectivity = async () => {
    try {
      const r = await conn.mutateAsync();
      const okN = r.td_keys.filter((k) => k.ok).length;
      toast(
        `connectivity: ${okN}/${r.td_keys.length} keys ok`,
        okN === r.td_keys.length ? "success" : "warn",
      );
    } catch (e) {
      toast(`connectivity falló — ${errMsg(e)}`, "error");
    }
  };

  const reportsList = reports.data?.items ?? [];

  return (
    <Box
      id={5}
      state={overall}
      title="Validator + diagnóstico"
      sub={
        <>
          batería D · A · B · C · E · F · G · histórico de reportes en DB · TXT en{" "}
          <span className="ref">LOG/</span> · 5 días retention
        </>
      }
      statusText={statusText}
    >
      <div className="toolbar">
        <span className="toolbar__left">
          corre la batería on-demand · histórico persiste en{" "}
          <span className="ref">/validator/reports</span>
        </span>
        <div className="toolbar__right">
          <button
            type="button"
            className="btn is-ghost"
            onClick={onConnectivity}
            disabled={conn.isPending || run.isPending}
          >
            {conn.isPending ? "probando…" : "solo conectividad"}
          </button>
          <button type="button" className="btn is-primary" onClick={onRun} disabled={run.isPending}>
            {run.isPending ? "corriendo…" : "correr validator"}
          </button>
        </div>
      </div>

      <div className="p5-grid">
        {/* IZQ — grid del Validator + histórico */}
        <div>
          <div className="val-block">
            <div className="val-block__head">
              <div>
                <div className="val-block__title">Batería D / A / B / C / E / F / G</div>
                <div className="val-block__sub">
                  grid 7 celdas · alimentado por WS <span className="ref">validator.progress</span>{" "}
                  (start + end por test)
                </div>
              </div>
              {progress.trigger ? (
                <Badge variant="run">trigger · {progress.trigger}</Badge>
              ) : lastReport.data ? (
                <Badge variant="default">trigger · {lastReport.data.trigger}</Badge>
              ) : null}
            </div>

            <div className={`val-bar ${barClass}`}>
              <i style={{ width: `${progressPct}%` }} />
            </div>
            <div className="val-bar__lbl">{lblText}</div>

            <div className="val-grid">
              {TEST_ORDER.map((t) => {
                const cellState = cellStates[t];
                const cls = cellState === "pend" ? "vg-cell is-pend" : `vg-cell is-${cellState}`;
                return (
                  <div key={t} className={cls}>
                    <div className="vg-cell__l">{t}</div>
                    <div className="vg-cell__n">{TEST_LABELS[t]}</div>
                    <div className="vg-cell__stat">
                      <i />
                    </div>
                  </div>
                );
              })}
            </div>

            <div className="val-msg">
              {progress.lastMessage ? (
                <span>{progress.lastMessage}</span>
              ) : lastReport.data ? (
                <span>último run · {new Date(lastReport.data.finished_at).toLocaleString()}</span>
              ) : (
                <span>sin reportes todavía · corré la batería para empezar</span>
              )}
            </div>
          </div>

          <div className="reports">
            <div className="reports__head">
              <span>histórico · /validator/reports</span>
              <span className="num">
                {reports.isLoading ? "…" : `${reportsList.length} reportes`}
              </span>
            </div>
            {reportsList.length === 0 ? (
              <div style={{ padding: 16, textAlign: "center", color: "var(--t-55)" }}>
                {reports.isLoading ? "cargando…" : "sin reportes históricos"}
              </div>
            ) : (
              reportsList.map((r) => {
                const dur = Math.round(
                  (new Date(r.finished_at).getTime() - new Date(r.started_at).getTime()) / 1000,
                );
                return (
                  <div key={r.run_id} className="rep-row">
                    <div>
                      <div className="rep-row__when">
                        {new Date(r.started_at).toLocaleString()}
                        <span className="dur">· {dur}s</span>
                      </div>
                      <div className="rep-row__meta">
                        <span className="rep-row__trig">{r.trigger}</span>
                        <span>{r.overall_status}</span>
                      </div>
                    </div>
                    <div className="rep-row__mini">
                      {/* mini-rep sin desglose por test (la list endpoint no
                          devuelve los `tests`); el detalle se carga al click,
                          deuda v2 — modal. */}
                      <i
                        className={
                          r.overall_status === "fail"
                            ? "is-fail"
                            : r.overall_status === "warning"
                              ? "is-warn"
                              : ""
                        }
                      />
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </div>

        {/* DER — Estado motores compacto */}
        <div>
          <div className="val-block">
            <div className="val-block__head">
              <div>
                <div className="val-block__title">Estado de motores</div>
                <div className="val-block__sub">resumen · detalle full en Dashboard</div>
              </div>
            </div>
            <div className="engines-mini">
              <div className="engine-row">
                <div className="engine-row__nm">
                  data engine <Pilot state={enginePilot(engineState.data)} />
                </div>
                <div className="engine-row__ms">
                  {engineState.messages.data || engineState.data}
                </div>
              </div>
              <div className="engine-row">
                <div className="engine-row__nm">
                  scoring <Pilot state={enginePilot(engineState.scoring)} />
                </div>
                <div className="engine-row__ms">
                  {engineState.messages.scoring || engineState.scoring}
                </div>
              </div>
              <div className="engine-row">
                <div className="engine-row__nm">
                  database <Pilot state={enginePilot(engineState.database)} />
                </div>
                <div className="engine-row__ms">
                  {engineState.messages.database || engineState.database}
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div className="note" style={{ marginTop: "var(--gap-3)" }}>
        el grid de 7 celdas se actualiza en vivo por WS{" "}
        <span className="accent">validator.progress</span> (2 events por test: running + end) · el
        histórico tiene cursor pagination en el backend · click en un reporte abre el detalle
        completo (deuda v2)
      </div>
    </Box>
  );
}
