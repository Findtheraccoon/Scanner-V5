import type { ValidatorProgressPayload, ValidatorTrigger } from "@/api/types";
import { create } from "zustand";

/* Estado del Validator alimentado por WS `validator.progress`. Acumula
   2 events por test (running + end) en un map por test_id. Cuando un
   run nuevo arranca (run_id distinto), se resetea el grid.

   El componente del Box 5 lee:
   - tests: estado por test (running / passed / warning / failed).
   - completedCount + totalCount: para la barra de progreso global.
   - lastMessage: mensaje del test más reciente (footer del block).

   Para el grid 7 celdas, el orden visual canónico (D · A · B · C · E · F · G)
   se aplica en el componente, no acá — el store guarda lo que llega. */

export type ValidatorTestRuntimeStatus = "pending" | "running" | "passed" | "warning" | "failed";

interface ValidatorProgressState {
  runId: string | null;
  trigger: ValidatorTrigger | null;
  tests: Record<string, ValidatorTestRuntimeStatus>;
  lastMessage: string | null;
  startedAt: number | null;
  finishedAt: number | null;

  applyProgress: (payload: ValidatorProgressPayload) => void;
  reset: () => void;
}

export const useValidatorProgressStore = create<ValidatorProgressState>((set) => ({
  runId: null,
  trigger: null,
  tests: {},
  lastMessage: null,
  startedAt: null,
  finishedAt: null,

  applyProgress: (p) =>
    set((s) => {
      const isNewRun = p.run_id !== s.runId;
      const tests = isNewRun ? {} : { ...s.tests };

      // El payload `status` del backend no es 1:1 con el del store —
      // mapeamos: "passed"/"warning"/"failed" se quedan; "running" también.
      tests[p.test] = p.status as ValidatorTestRuntimeStatus;

      const allTerminal = Object.values(tests).every(
        (st) => st === "passed" || st === "warning" || st === "failed",
      );

      return {
        runId: p.run_id,
        trigger: p.trigger,
        tests,
        lastMessage: p.message ?? null,
        startedAt: isNewRun ? Date.now() : s.startedAt,
        finishedAt: allTerminal ? Date.now() : null,
      };
    }),

  reset: () =>
    set({
      runId: null,
      trigger: null,
      tests: {},
      lastMessage: null,
      startedAt: null,
      finishedAt: null,
    }),
}));
