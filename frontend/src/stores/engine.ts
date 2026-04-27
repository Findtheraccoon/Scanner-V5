import type { EngineStatusLevel, EngineStatusPayload } from "@/api/types";
import { create } from "zustand";

export type WsConnectionState = "disconnected" | "connecting" | "connected" | "error";

interface EngineState {
  /* Estado por motor — alimentado por eventos `engine.status` del WS y por
     `GET /engine/health` al arrancar. */
  data: EngineStatusLevel;
  scoring: EngineStatusLevel;
  database: EngineStatusLevel;
  validator: EngineStatusLevel;
  /* Sub-estado del data engine: cuando está pausado por toggle AUTO. */
  dataPaused: boolean;
  /* Último mensaje + código de error por motor (para tooltips/toasts). */
  messages: Partial<Record<EngineStatusPayload["engine"], string>>;
  errorCodes: Partial<Record<EngineStatusPayload["engine"], string>>;
  /* Estado de la conexión WS — UI lo refleja en el indicador "live". */
  ws: WsConnectionState;

  applyEngineStatus: (payload: EngineStatusPayload) => void;
  setWsState: (state: WsConnectionState) => void;
  setDataPaused: (paused: boolean) => void;
}

export const useEngineStore = create<EngineState>((set) => ({
  data: "green",
  scoring: "green",
  database: "green",
  validator: "green",
  dataPaused: false,
  messages: {},
  errorCodes: {},
  ws: "disconnected",
  applyEngineStatus: (p) =>
    set((s) => {
      const isPause = p.engine === "data" && p.status === "paused";
      // Si llega "paused" del data engine, mantenemos status visible (yellow)
      // pero marcamos el flag dataPaused para que la UI distinga.
      const visibleStatus: EngineStatusLevel = isPause ? "yellow" : p.status;
      return {
        [p.engine]: visibleStatus,
        dataPaused: p.engine === "data" ? isPause : s.dataPaused,
        messages: { ...s.messages, [p.engine]: p.message ?? "" },
        errorCodes: { ...s.errorCodes, [p.engine]: p.error_code ?? "" },
      } as Partial<EngineState>;
    }),
  setWsState: (ws) => set({ ws }),
  setDataPaused: (paused) => set({ dataPaused: paused }),
}));
