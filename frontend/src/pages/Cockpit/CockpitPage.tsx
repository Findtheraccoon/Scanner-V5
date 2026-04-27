import { useEngineHealth, useLatestSignal, useSlots } from "@/api/queries";
import { DevStateSwitcher } from "@/components/Dev/DevStateSwitcher";
import { useAuthStore } from "@/stores/auth";
import { useSignalsStore } from "@/stores/signals";
import { useSlotsStore } from "@/stores/slots";
import { useEffect } from "react";
import { Panel } from "./Panel";
import { useCockpitState } from "./StateToast";
import { Watchlist } from "./Watchlist";
import "./cockpit.css";

export function CockpitPage() {
  const selectedId = useSlotsStore((s) => s.selectedSlotId);
  const cockpit = useCockpitState();
  const token = useAuthStore((s) => s.token);

  // Hidrata la señal del slot seleccionado en el store cuando cambia.
  const latestQuery = useLatestSignal(selectedId);
  const applySignal = useSignalsStore((s) => s.applySignal);
  useEffect(() => {
    if (latestQuery.data) applySignal(latestQuery.data);
  }, [latestQuery.data, applySignal]);

  // El estado "loading" se infiere de las queries iniciales — sólo aplica
  // cuando hay token (con el bearer cargado pero el backend aún no respondió).
  const slotsQuery = useSlots();
  const healthQuery = useEngineHealth();
  const isLoading =
    token !== null && cockpit.state === "normal" && (slotsQuery.isLoading || healthQuery.isLoading);

  const effectiveState = isLoading ? "loading" : cockpit.state;
  const className = effectiveState === "normal" ? "main" : `main cockpit--${effectiveState}`;

  return (
    <main className={className}>
      <Watchlist />
      <Panel cockpitState={effectiveState} ticker={cockpit.ticker} />
      <DevStateSwitcher />
    </main>
  );
}
