import type { SignalConfidence, SignalDirection, SlotInfo } from "@/api/types";
import { useSignalsStore } from "@/stores/signals";
import { useSlotsStore } from "@/stores/slots";
import { Slot } from "./Slot";
import type { SlotData } from "./data";

/* Combina datos del backend (slots + signals) en cards listas para
   render por <Slot>. UX-003: sin contenido falso — si el backend no
   devolvió slots, mostramos 6 cards vacías estructurales; si hay
   ticker pero no signal, dejamos band/score/sparkline en null. La
   sparkline real llegará con Lightweight Charts en una iteración
   posterior; mientras tanto se renderiza vacía. */
interface WatchlistSignalSlim {
  conf: SignalConfidence;
  dir: SignalDirection | null;
  score: number;
  // BUG-023: WR@30 del backtest training para la banda de la signal,
  // inyectado por el backend desde `<fixture>.metrics.json`.
  wr_pct?: number | null;
}

function buildSlotData(
  registrySlots: SlotInfo[],
  signals: Record<number, WatchlistSignalSlim>,
): SlotData[] {
  if (registrySlots.length === 0) {
    return Array.from({ length: 6 }, (_, idx) => ({
      id: idx + 1,
      ticker: null,
      band: null,
      direction: null,
      score: null,
      winRate: null,
      selected: false,
      metallic: false,
      sparkline: null,
    }));
  }
  return registrySlots.slice(0, 6).map((s) => {
    const sig = signals[s.slot_id];
    return {
      id: s.slot_id,
      ticker: s.ticker,
      band: sig ? sig.conf : null,
      direction: sig?.dir ?? null,
      score: sig?.score ?? null,
      // BUG-023: pasamos el WR del backtest si vino en la signal.
      // Slot.tsx lo renderiza como `{wr}%` cuando hay setup.
      winRate:
        sig?.wr_pct !== null && sig?.wr_pct !== undefined
          ? Math.round(sig.wr_pct)
          : null,
      selected: false,
      metallic: sig?.conf === "S+",
      sparkline: null,
    };
  });
}

export function Watchlist() {
  const registrySlots = useSlotsStore((s) => s.slots);
  const selectedId = useSlotsStore((s) => s.selectedSlotId);
  const select = useSlotsStore((s) => s.selectSlot);
  const signals = useSignalsStore((s) => s.bySlot);

  const slots = buildSlotData(
    registrySlots,
    Object.fromEntries(
      Object.entries(signals).map(([k, v]) => [
        Number(k),
        { conf: v.conf, dir: v.dir, score: v.score, wr_pct: v.wr_pct },
      ]),
    ),
  ).map((s) => ({ ...s, selected: s.id === selectedId }));

  const filledCount = slots.filter((s) => s.ticker).length;

  return (
    <aside className="watchlist" aria-label="watchlist">
      <header className="wl-header">
        <span className="wl-title">watchlist</span>
        <span className="wl-count">
          {String(filledCount).padStart(2, "0")} / {String(slots.length).padStart(2, "0")}
        </span>
      </header>
      <div className="slot-list">
        {slots.map((slot) => (
          <Slot key={slot.id} slot={slot} onSelect={select} />
        ))}
      </div>
    </aside>
  );
}
