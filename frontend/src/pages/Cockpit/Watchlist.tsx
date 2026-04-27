import { Slot } from "./Slot";
import { SLOTS } from "./data";

interface WatchlistProps {
  selectedId: number;
  onSelect: (id: number) => void;
}

export function Watchlist({ selectedId, onSelect }: WatchlistProps) {
  const slots = SLOTS.map((s) => ({ ...s, selected: s.id === selectedId }));
  const filledCount = slots.filter((s) => s.ticker).length;

  return (
    <aside className="watchlist" aria-label="watchlist">
      <header className="wl-header">
        <span className="wl-title">watchlist</span>
        <span className="wl-count">
          {String(filledCount).padStart(2, "0")} / {String(SLOTS.length).padStart(2, "0")}
        </span>
      </header>
      <div className="slot-list">
        {slots.map((slot) => (
          <Slot key={slot.id} slot={slot} onSelect={onSelect} />
        ))}
      </div>
    </aside>
  );
}
