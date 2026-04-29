import { useApiUsageStore } from "@/stores/apiUsage";
import { useAuthStore } from "@/stores/auth";
import { useEngineStore } from "@/stores/engine";
import { useSignalsStore } from "@/stores/signals";
import { useSlotsStore } from "@/stores/slots";
import { useValidatorProgressStore } from "@/stores/validatorProgress";
import { useEffect } from "react";
import type {
  ApiUsageTickPayload,
  EngineStatusPayload,
  SignalPayload,
  SlotStatusPayload,
  SystemLogPayload,
  ValidatorProgressPayload,
  WsEnvelope,
} from "./types";

const RECONNECT_BACKOFFS_MS = [1000, 2000, 4000, 8000, 16000];

/* Conecta a `/ws?token=<bearer>`, dispatches a stores. Auto-reconnect con
   backoff exponencial. Idempotente: invocaciones múltiples del hook mientras
   el componente está vivo no abren conexiones extras. */
export function useScannerWS(): void {
  const token = useAuthStore((s) => s.token);

  useEffect(() => {
    if (!token) {
      useEngineStore.getState().setWsState("disconnected");
      return;
    }

    let socket: WebSocket | null = null;
    let attempt = 0;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
    let cancelled = false;

    const connect = () => {
      if (cancelled) return;
      const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
      const url = `${proto}//${window.location.host}/ws?token=${encodeURIComponent(token)}`;
      useEngineStore.getState().setWsState("connecting");
      const s = new WebSocket(url);
      socket = s;

      s.onopen = () => {
        attempt = 0;
        useEngineStore.getState().setWsState("connected");
      };

      s.onmessage = (ev) => {
        try {
          const env = JSON.parse(ev.data) as WsEnvelope;
          dispatch(env);
        } catch {
          // payload mal formado — ignorar
        }
      };

      s.onerror = () => {
        useEngineStore.getState().setWsState("error");
      };

      s.onclose = () => {
        useEngineStore.getState().setWsState("disconnected");
        if (cancelled) return;
        const delay = RECONNECT_BACKOFFS_MS[Math.min(attempt, RECONNECT_BACKOFFS_MS.length - 1)];
        attempt += 1;
        reconnectTimer = setTimeout(connect, delay);
      };
    };

    connect();

    return () => {
      cancelled = true;
      if (reconnectTimer !== null) clearTimeout(reconnectTimer);
      if (socket && socket.readyState <= WebSocket.OPEN) socket.close();
    };
  }, [token]);
}

function dispatch(env: WsEnvelope): void {
  switch (env.event) {
    case "signal.new":
      useSignalsStore.getState().applySignal(env.payload as SignalPayload);
      break;
    case "slot.status":
      useSlotsStore.getState().applySlotStatus(env.payload as SlotStatusPayload);
      break;
    case "engine.status":
      useEngineStore.getState().applyEngineStatus(env.payload as EngineStatusPayload);
      break;
    case "api_usage.tick":
      useApiUsageStore.getState().applyTick(env.payload as ApiUsageTickPayload);
      break;
    case "validator.progress":
      useValidatorProgressStore
        .getState()
        .applyProgress(env.payload as ValidatorProgressPayload);
      break;
    case "system.log":
      // no-op por ahora; útil para Dashboard cuando lleguemos.
      void (env.payload as SystemLogPayload);
      break;
  }
}
