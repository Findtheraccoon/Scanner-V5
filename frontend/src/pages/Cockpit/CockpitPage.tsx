import { useLatestSignal } from "@/api/queries";
import { useSignalsStore } from "@/stores/signals";
import { useSlotsStore } from "@/stores/slots";
import { useEffect } from "react";
import { Panel } from "./Panel";
import { useCockpitState } from "./StateToast";
import { Watchlist } from "./Watchlist";
import "./cockpit.css";

export function CockpitPage() {
  const selectedId = useSlotsStore((s) => s.selectedSlotId);
  const { state, ticker } = useCockpitState();

  // Hidrata la señal del slot seleccionado en el store cuando cambia.
  const latestQuery = useLatestSignal(selectedId);
  const applySignal = useSignalsStore((s) => s.applySignal);
  useEffect(() => {
    if (latestQuery.data) applySignal(latestQuery.data);
  }, [latestQuery.data, applySignal]);

  const className = state === "normal" ? "main" : `main cockpit--${state}`;

  return (
    <main className={className}>
      <Watchlist />
      <Panel cockpitState={state} ticker={ticker} />
    </main>
  );
}
