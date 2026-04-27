import { Sparkline } from "./Sparkline";
import type { SlotData } from "./data";

interface SlotProps {
  slot: SlotData;
  onSelect?: (id: number) => void;
}

export function Slot({ slot, onSelect }: SlotProps) {
  if (!slot.ticker) {
    return (
      <article className="slot--empty" data-slot={slot.id}>
        + agregar slot
      </article>
    );
  }

  const className = ["slot", slot.selected ? "is-selected" : ""].filter(Boolean).join(" ");
  const bookmarkClassName = ["bookmark", slot.metallic ? "bookmark--metallic" : ""]
    .filter(Boolean)
    .join(" ");

  return (
    <article
      className={className}
      data-slot={slot.id}
      onClick={onSelect ? () => onSelect(slot.id) : undefined}
      onKeyDown={
        onSelect
          ? (e) => {
              if (e.key === "Enter" || e.key === " ") onSelect(slot.id);
            }
          : undefined
      }
      // biome-ignore lint/a11y/useSemanticElements: <article> conserva la semántica del Hi-Fi v2; un <button> rompería el layout de bookmark + sparkline absolutos
      // biome-ignore lint/a11y/noNoninteractiveElementToInteractiveRole: ver comentario superior — el role/tabIndex hacen la card cliqueable + accesible por teclado
      role="button"
      tabIndex={0}
    >
      {slot.band ? (
        <span className={bookmarkClassName} data-band={slot.band}>
          {slot.metallic ? <span className="metal-sweep" /> : null}
          <span>{slot.band}</span>
        </span>
      ) : null}
      <div className="slot__row">
        <div className="slot__head">
          <span className="slot__id">{String(slot.id).padStart(2, "0")}</span>
          <span className="slot__ticker">{slot.ticker}</span>
        </div>
        <div className="slot__bottom">
          <span className="slot__dirline">
            <span className="slot__dir" data-dir={slot.direction}>
              <span className="slot__dir-arrow">{slot.direction === "PUT" ? "▼" : "▲"}</span>{" "}
              {slot.direction}
            </span>
          </span>
          <span className="slot__metrics">
            <span className="slot__score">{slot.score?.toFixed(1)}</span>
            <span className="slot__wr">{slot.winRate}%</span>
          </span>
        </div>
      </div>
      {slot.sparkline ? (
        <div className="slot__spark">
          <Sparkline data={slot.sparkline} />
        </div>
      ) : null}
    </article>
  );
}
