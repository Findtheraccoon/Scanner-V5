import { useToast } from "@/components/Toast/ToastProvider";
import { CHAT_FORMAT_FALLBACK } from "@/lib/chatFormat";
import { copyToClipboard } from "@/lib/copyToClipboard";
import { useEngineStore } from "@/stores/engine";
import { useSignalsStore } from "@/stores/signals";
import { useSlotsStore } from "@/stores/slots";
import { useState } from "react";
import { type CockpitState, StateToasts } from "./StateToast";
import { useEffectiveSlot } from "./useEffectiveSlot";

interface PanelProps {
  cockpitState?: CockpitState;
  ticker?: string | null;
}

/* Panel del Cockpit — banner sticky + resumen ejecutivo + gráfico + detalle.

   UX-003: cuando no hay signal real cargada (slot vacío, motores
   offline, sin backend), todos los valores numéricos se muestran como
   `—`. NO mostramos fake data del Hi-Fi v2 — el usuario debe ver el
   estado real (loading / vacío) en lugar de creer que el sistema está
   reportando datos. */
export function Panel({ cockpitState = "normal", ticker = null }: PanelProps) {
  const [detailOpen, setDetailOpen] = useState(false);
  const selectedId = useSlotsStore((s) => s.selectedSlotId);
  const signal = useSignalsStore((s) => s.bySlot[selectedId]);
  const dataEngine = useEngineStore((s) => s.data);

  const hasSignal = signal != null;
  const hasEngine = dataEngine === "green" || dataEngine === "yellow" || dataEngine === "paused";

  return (
    <section className="panel" aria-label="detalle">
      <StateToasts state={cockpitState} ticker={ticker} />
      <Banner hasSignal={hasSignal} />
      <Exec hasSignal={hasSignal} hasEngine={hasEngine} />
      <Chart hasSignal={hasSignal} hasEngine={hasEngine} />
      <Detail open={detailOpen} onToggle={() => setDetailOpen((v) => !v)} hasSignal={hasSignal} />
    </section>
  );
}

function Banner({ hasSignal }: { hasSignal: boolean }) {
  const toast = useToast();
  const [copied, setCopied] = useState(false);
  const selectedId = useSlotsStore((s) => s.selectedSlotId);
  const effective = useEffectiveSlot(selectedId);
  const signal = useSignalsStore((s) => s.bySlot[selectedId]);

  const ticker = effective.ticker ?? "—";
  const slotIdStr = String(selectedId).padStart(2, "0");

  const chatText = signal?.chat_format ?? CHAT_FORMAT_FALLBACK;

  const handleCopy = async () => {
    if (!effective.ticker) {
      toast.push("slot vacío — nada que copiar", "warn");
      return;
    }
    if (!hasSignal) {
      toast.push("sin señal cargada — nada que copiar", "warn");
      return;
    }
    const ok = await copyToClipboard(chatText);
    if (ok) {
      setCopied(true);
      toast.push("✓ copiado al portapapeles", "success");
      setTimeout(() => setCopied(false), 2000);
    } else {
      toast.push("no se pudo copiar al portapapeles", "error");
    }
  };

  // Slot vacío — banner placeholder con texto neutro.
  if (!effective.ticker) {
    return (
      <header className="banner" data-band="REVISAR">
        <span className="banner__ghost" aria-hidden="true">
          ···
        </span>
        <div className="banner__row">
          <div className="banner__id">
            <h1 className="banner__ticker">slot {slotIdStr}</h1>
            <div className="banner__order2">
              <span className="banner__signal" style={{ color: "var(--t-55)" }}>
                vacío
              </span>
            </div>
            <div className="banner__order3">
              <span>+ agregar slot desde Configuración → Slot Registry</span>
            </div>
          </div>
        </div>
      </header>
    );
  }

  // Slot con ticker pero SIN signal cargada — mostramos ticker + estado loading.
  if (!hasSignal) {
    return (
      <header className="banner" data-band="REVISAR">
        <span className="banner__ghost" aria-hidden="true">
          {ticker}
        </span>
        <div className="banner__row">
          <div className="banner__id">
            <h1 className="banner__ticker">{ticker}</h1>
            <div className="banner__order2">
              <span className="banner__signal" style={{ color: "var(--t-55)" }}>
                esperando señal
              </span>
            </div>
            <div className="banner__order3">
              <span>{tickerCaption(ticker)}</span>
              <span className="sep">·</span>
              <span>slot {slotIdStr}</span>
            </div>
          </div>
        </div>
      </header>
    );
  }

  // Hay signal real — mostramos todo.
  const band = signal.conf;
  const dir = signal.dir ?? "CALL";
  const score = signal.score;
  const label = signal.signal;
  const fixtureId = effective.fixtureId ?? signal.fixture_id ?? "—";

  return (
    <header className="banner" data-band={band}>
      <span className="banner__ghost" aria-hidden="true">
        {ticker}
      </span>
      <div className="banner__row">
        <div className="banner__id">
          <h1 className="banner__ticker">{ticker}</h1>
          <div className="banner__order2">
            <span className="banner__band" data-band={band}>
              <span>{band}</span>
            </span>
            <span className="banner__dir">{dir}</span>
            <span className="banner__score">
              score <b>{score.toFixed(1)}</b>
            </span>
            <span className="banner__signal">{label.toLowerCase()}</span>
          </div>
          <div className="banner__order3">
            <span>{tickerCaption(ticker)}</span>
            <span className="sep">·</span>
            <span>slot {slotIdStr}</span>
            <span className="sep">·</span>
            <span>fixture {fixtureId}</span>
          </div>
        </div>
        <button
          type="button"
          className={copied ? "btn-copy is-copied" : "btn-copy"}
          aria-label="copiar señal"
          onClick={handleCopy}
        >
          <svg
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden="true"
          >
            <title>copiar</title>
            <rect x="8" y="8" width="12" height="12" rx="2" />
            <path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2" />
          </svg>
          <span className="btn-copy__label">{copied ? "copiado" : "copiar"}</span>
        </button>
      </div>
    </header>
  );
}

const TICKER_NAMES: Record<string, string> = {
  SPY: "s&p 500 etf",
  QQQ: "nasdaq 100 etf",
  IWM: "russell 2000 etf",
  AAPL: "apple inc",
  NVDA: "nvidia corp",
  MSFT: "microsoft corp",
  TSLA: "tesla inc",
  AMZN: "amazon.com inc",
};

function tickerCaption(ticker: string): string {
  return TICKER_NAMES[ticker.toUpperCase()] ?? ticker.toLowerCase();
}

interface DataAvailabilityProps {
  hasSignal: boolean;
  hasEngine: boolean;
}

/* Resumen ejecutivo · 6 chips. UX-003: sin signal cargada → todos los
   valores son `—`. Cuando llegue la señal real del backend con
   `layers` poblados, los chips se rellenan con datos del payload. */
function Exec({ hasSignal, hasEngine }: DataAvailabilityProps) {
  if (!hasSignal) {
    return (
      <section className="exec" aria-label="resumen ejecutivo">
        <div className="exec__grid">
          <div className="exec__price">
            <div className="exec__price-label">último</div>
            <div className="exec__price-num" style={{ color: "var(--t-38)" }}>
              —
            </div>
            <div className="exec__price-chg" style={{ color: "var(--t-38)" }}>
              {hasEngine ? "esperando vela" : "motores offline"}
            </div>
          </div>
          <div className="exec__chips">
            <Chip label="alineación">—</Chip>
            <Chip label="atr 15M">—</Chip>
            <Chip label="vela">—</Chip>
            <Chip label="resistencias">—</Chip>
            <Chip label="soportes">—</Chip>
            <Chip label="vol mediana 15M">—</Chip>
          </div>
        </div>
      </section>
    );
  }

  // Hay signal — los `layers` del SignalPayload contienen los datos
  // específicos. Por ahora mostramos solo lo que el shape del payload
  // garantiza; los demás chips quedan en "—" hasta que el backend
  // estructure el `layers` para consumo del frontend.
  return (
    <section className="exec" aria-label="resumen ejecutivo">
      <div className="exec__grid">
        <div className="exec__price">
          <div className="exec__price-label">último</div>
          <div className="exec__price-num">—</div>
          <div className="exec__price-chg">esperando layer · precio</div>
        </div>
        <div className="exec__chips">
          <Chip label="alineación">—</Chip>
          <Chip label="atr 15M">—</Chip>
          <Chip label="vela">—</Chip>
          <Chip label="resistencias">—</Chip>
          <Chip label="soportes">—</Chip>
          <Chip label="vol mediana 15M">—</Chip>
        </div>
      </div>
    </section>
  );
}

function Chip({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="chip">
      <span className="chip__label">{label}</span>
      <span className="chip__val" style={{ color: "var(--t-55)" }}>
        {children}
      </span>
    </div>
  );
}

/* Chart · UX-003: sin signal cargada → placeholder vacío con grilla
   pero sin las 3 líneas de MAs ni los precios del eje Y. */
function Chart({ hasSignal, hasEngine }: DataAvailabilityProps) {
  return (
    <section className="chart" aria-label="gráfico ticker">
      <div className="chart__head">
        <span className="chart__title">
          <b>—</b>
          <span style={{ color: "var(--t-38)" }}>
            {hasSignal
              ? "datos del chart pendientes"
              : hasEngine
                ? "esperando primera vela"
                : "motores offline"}
          </span>
        </span>
      </div>
      <div className="chart__canvas">
        <svg viewBox="0 0 920 240" preserveAspectRatio="none" aria-hidden="true">
          <title>chart</title>
          <g stroke="rgba(255,255,255,0.04)" strokeWidth="1">
            <line x1="0" y1="40" x2="920" y2="40" />
            <line x1="0" y1="80" x2="920" y2="80" />
            <line x1="0" y1="120" x2="920" y2="120" />
            <line x1="0" y1="160" x2="920" y2="160" />
            <line x1="0" y1="200" x2="920" y2="200" />
          </g>
          <text
            x="460"
            y="125"
            textAnchor="middle"
            fill="rgba(255,255,255,0.18)"
            fontSize="11"
            fontFamily="var(--font-mono)"
          >
            sin datos
          </text>
        </svg>
        <div className="chart__yaxis">
          <span>—</span>
          <span>—</span>
          <span>—</span>
          <span>—</span>
          <span>—</span>
        </div>
      </div>
    </section>
  );
}

interface DetailProps {
  open: boolean;
  onToggle: () => void;
  hasSignal: boolean;
}

/* Detalle técnico · UX-003: sin signal cargada → mensaje "esperando
   datos" en lugar de los bloques con valores fake. */
function Detail({ open, onToggle, hasSignal }: DetailProps) {
  return (
    <section className="detail" aria-label="detalle técnico">
      <div className="detail__head">
        <span className="detail__title">detalle técnico</span>
        <button type="button" className="detail__toggle" onClick={onToggle}>
          <span className="label">{open ? "colapsar" : "expandir"}</span>
          <span className="arrow">{open ? "▴" : "▾"}</span>
        </button>
      </div>
      <div className="detail__grid" hidden={!open}>
        {!hasSignal ? (
          <div
            style={{
              gridColumn: "1 / -1",
              padding: "32px 16px",
              textAlign: "center",
              color: "var(--t-55)",
              fontFamily: "var(--font-mono)",
              fontSize: "11px",
            }}
          >
            sin señal cargada · esperando datos del backend
          </div>
        ) : (
          <div
            style={{
              gridColumn: "1 / -1",
              padding: "32px 16px",
              textAlign: "center",
              color: "var(--t-55)",
              fontFamily: "var(--font-mono)",
              fontSize: "11px",
            }}
          >
            datos del detalle pendientes — el backend estructurará el `layers` del SignalPayload
            para consumo del frontend en una iteración siguiente
          </div>
        )}
      </div>
    </section>
  );
}
