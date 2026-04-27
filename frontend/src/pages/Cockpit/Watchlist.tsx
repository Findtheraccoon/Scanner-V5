import type { SignalConfidence, SignalDirection, SlotInfo } from "@/api/types";
import { useSignalsStore } from "@/stores/signals";
import { useSlotsStore } from "@/stores/slots";
import { Slot } from "./Slot";
import { SLOTS as FALLBACK_SLOTS, type SlotData } from "./data";

const PLACEHOLDER_SPARK = FALLBACK_SLOTS;

/* Combina datos del backend (slots + signals) con fallback hardcoded del
   Hi-Fi v2. Mientras no hay datos del backend, muestra los 6 placeholders
   originales — preserva el "look" del scaffold inicial. */
function buildSlotData(
  registrySlots: SlotInfo[],
  signals: Record<number, { conf: SignalConfidence; dir: SignalDirection | null; score: number }>,
): SlotData[] {
  if (registrySlots.length === 0) return PLACEHOLDER_SPARK;
  return registrySlots.slice(0, 6).map((s, idx) => {
    const placeholder = PLACEHOLDER_SPARK[idx] ?? PLACEHOLDER_SPARK[0];
    const sig = signals[s.slot_id];
    if (!s.ticker) {
      return { ...placeholder, id: s.slot_id, ticker: null, band: null, sparkline: null };
    }
    return {
      id: s.slot_id,
      ticker: s.ticker,
      band: sig ? sig.conf : placeholder.band,
      direction: sig?.dir ?? "CALL",
      score: sig?.score ?? null,
      winRate: null,
      selected: false,
      metallic: sig?.conf === "S+",
      sparkline: placeholder.sparkline,
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
        { conf: v.conf, dir: v.dir, score: v.score },
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
