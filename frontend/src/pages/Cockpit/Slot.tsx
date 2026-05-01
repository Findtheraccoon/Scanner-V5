import type { SignalConfidence } from "@/api/types";
import { useScanningStore } from "@/stores/scanning";
import { Sparkline } from "./Sparkline";
import type { SlotData } from "./data";

interface SlotProps {
  slot: SlotData;
  onSelect?: (id: number) => void;
}

/* Spec del Hi-Fi v2: el bookmark de tier sólo aparece para setups
   destacados (A / A+ / S / S+). En B y REVISAR el tier se infiere del
   score numérico que ya está visible en la métrica de la card. */
const BOOKMARK_BANDS: ReadonlySet<SignalConfidence> = new Set(["A", "A+", "S", "S+"]);

function showsBookmark(band: SignalConfidence | null): band is SignalConfidence {
  return band !== null && BOOKMARK_BANDS.has(band);
}

export function Slot({ slot, onSelect }: SlotProps) {
  const isScanning = useScanningStore((s) => s.active.has(slot.id));

  if (!slot.ticker) {
    return (
      <article className="slot--empty" data-slot={slot.id}>
        + agregar slot
      </article>
    );
  }

  const className = ["slot", slot.selected ? "is-selected" : "", isScanning ? "is-scanning" : ""]
    .filter(Boolean)
    .join(" ");
  const bookmarkClassName = ["bookmark", slot.metallic ? "bookmark--metallic" : ""]
    .filter(Boolean)
    .join(" ");
  const renderBookmark = showsBookmark(slot.band);
  // UX-003: si no hay signal cargada, no inventamos dir/score/winRate;
  // mostramos un caption "esperando señal" en lugar del bottom row.
  const hasSignalData = slot.band !== null && slot.direction !== null && slot.score !== null;

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
      {renderBookmark ? (
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
        {hasSignalData ? (
          <div className="slot__bottom">
            <span className="slot__dirline">
              <span className="slot__dir" data-dir={slot.direction}>
                <span className="slot__dir-arrow">{slot.direction === "PUT" ? "▼" : "▲"}</span>{" "}
                {slot.direction}
              </span>
            </span>
            <span className="slot__metrics">
              <span className="slot__score">{slot.score?.toFixed(1)}</span>
              {slot.winRate !== null ? (
                <span
                  className="slot__wr"
                  title="WR @ banda · backtest training del canonical"
                >
                  {slot.winRate}% <small style={{ opacity: 0.6 }}>prob</small>
                </span>
              ) : null}
            </span>
          </div>
        ) : (
          <div className="slot__bottom slot__bottom--empty">
            <span className="slot__waiting">esperando señal</span>
          </div>
        )}
      </div>
      {slot.sparkline ? (
        <div className="slot__spark">
          <Sparkline data={slot.sparkline} />
        </div>
      ) : null}
    </article>
  );
}
