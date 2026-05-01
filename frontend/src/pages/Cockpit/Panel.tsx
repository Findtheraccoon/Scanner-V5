import { useCandles } from "@/api/queries";
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
  // BUG-018: `signal.signal` es boolean (¿se emitió?), no string. La
  // etiqueta visible se deriva del confidence band: "—" → NEUTRAL,
  // "REVISAR" → REVISAR, cualquier otra (B/A/A+/S/S+) → SETUP.
  const label =
    band === "—" || !signal.signal
      ? "NEUTRAL"
      : band === "REVISAR"
        ? "REVISAR"
        : "SETUP";
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

/* BUG-025: Exec ahora lee del signal real (layers + ind del backend).

   - PRECIO: ind.price (last close 15m, enriquecido por backend
     `_enrich_with_last_price` cuando ind viene vacío en blocked/NEUTRAL).
   - ALINEACIÓN: layers.alignment.{n,dir} → "3/3 bullish".
   - ATR 15M: ind.atr_15m (absoluto + % vs precio).
   - VELA: ind.gap_info.gap_pct o el cuerpo del último candle.
   - RESISTENCIAS: ind.bb_1h[0] (sup) o triggers con price ref.
   - SOPORTES: ind.bb_1h[2] (inf) o triggers con price ref.
   - VOL MEDIANA: ind.gap_info.vol_x si está disponible.

   Si la signal viene con campos faltantes (ej. blocked sin layers
   computados), cada chip se queda en "—" individualmente — degradación
   granular en lugar de pintar todo vacío. */
function Exec({ hasSignal, hasEngine }: DataAvailabilityProps) {
  const selectedId = useSlotsStore((s) => s.selectedSlotId);
  const signal = useSignalsStore((s) => s.bySlot[selectedId]);

  if (!hasSignal || !signal) {
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

  const layers = (signal.layers ?? {}) as Record<string, unknown>;
  const ind = ((signal as unknown as { ind?: Record<string, unknown> }).ind ??
    {}) as Record<string, unknown>;

  const price = typeof ind.price === "number" ? (ind.price as number) : null;
  const atr15 = typeof ind.atr_15m === "number" ? (ind.atr_15m as number) : null;
  const atrPct = price !== null && atr15 !== null ? (atr15 / price) * 100 : null;

  const aln = (layers.alignment ?? {}) as { n?: number; dir?: string };
  const alnText = aln.n !== undefined ? `${aln.n}/3 ${aln.dir ?? ""}`.trim() : "—";

  const bb1h = Array.isArray(ind.bb_1h) ? (ind.bb_1h as number[]) : null;
  const resistance = bb1h && bb1h.length === 3 ? bb1h[0] : null;
  const support = bb1h && bb1h.length === 3 ? bb1h[2] : null;

  const gap = (ind.gap_info ?? {}) as { gap_pct?: number; vol_x?: number };
  const velaText =
    typeof gap.gap_pct === "number" ? `${(gap.gap_pct * 100).toFixed(2)}%` : "—";
  const volText =
    typeof gap.vol_x === "number" ? `${gap.vol_x.toFixed(1)}×` : "—";

  // BUG-031: probabilidad de la banda según el backtest training del
  // canonical (signal.wr_pct, inyectado por backend desde
  // <fixture>.metrics.json). Si la signal está blocked/NEUTRAL el conf
  // es "—" y wr_pct viene null → chip muestra "—".
  const wr = (signal as unknown as { wr_pct?: number | null }).wr_pct;
  const probText =
    typeof wr === "number"
      ? `${wr.toFixed(1)}% @ ${signal.conf}`
      : "—";

  return (
    <section className="exec" aria-label="resumen ejecutivo">
      <div className="exec__grid">
        <div className="exec__price">
          <div className="exec__price-label">último</div>
          <div className="exec__price-num">
            {price !== null ? `$${price.toFixed(2)}` : "—"}
          </div>
          <div className="exec__price-chg" style={{ color: "var(--t-55)" }}>
            score <b>{signal.score.toFixed(1)}</b>
          </div>
        </div>
        <div className="exec__chips">
          <Chip label="probabilidad">{probText}</Chip>
          <Chip label="alineación">{alnText}</Chip>
          <Chip label="atr 15M">
            {atr15 !== null && atrPct !== null
              ? `${atrPct.toFixed(2)}% ($${atr15.toFixed(2)})`
              : "—"}
          </Chip>
          <Chip label="vela">{velaText}</Chip>
          <Chip label="resistencias">
            {resistance !== null ? `$${resistance.toFixed(2)}` : "—"}
          </Chip>
          <Chip label="soportes">
            {support !== null ? `$${support.toFixed(2)}` : "—"}
          </Chip>
          <Chip label="vol mediana 15M">{volText}</Chip>
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

/* Chart · BUG-022: sparkline OHLC mínimo desde candles_15m.
   Trae las últimas 50 velas via `useCandles(ticker)` y dibuja:
   - Línea de cierres (banda principal)
   - Wicks (high/low) + cuerpos (open→close) ultra-finos por candle
   - 5 etiquetas de precio en el eje Y
   La integración con Lightweight Charts queda como deuda futura. */
function Chart({ hasSignal, hasEngine }: DataAvailabilityProps) {
  const selectedId = useSlotsStore((s) => s.selectedSlotId);
  const effective = useEffectiveSlot(selectedId);
  const ticker = effective.ticker;
  const { data, isLoading } = useCandles(ticker, "15m", 50);
  const candles = data?.candles ?? [];
  const ready = candles.length >= 2;

  if (!ready) {
    const msg = !hasEngine
      ? "motores offline"
      : !ticker
        ? "sin slot seleccionado"
        : isLoading
          ? "cargando velas…"
          : hasSignal
            ? "esperando primera vela"
            : "sin datos · dispará un scan";
    return (
      <section className="chart" aria-label="gráfico ticker">
        <div className="chart__head">
          <span className="chart__title">
            <b>—</b>
            <span style={{ color: "var(--t-38)" }}>{msg}</span>
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
            <text x="460" y="125" textAnchor="middle"
              fill="rgba(255,255,255,0.18)" fontSize="11"
              fontFamily="var(--font-mono)">
              {isLoading ? "cargando…" : "sin datos"}
            </text>
          </svg>
          <div className="chart__yaxis">
            <span>—</span><span>—</span><span>—</span><span>—</span><span>—</span>
          </div>
        </div>
      </section>
    );
  }

  // Domain: precio min/max sobre TODA la ventana
  const lows = candles.map((k) => k.l);
  const highs = candles.map((k) => k.h);
  const minP = Math.min(...lows);
  const maxP = Math.max(...highs);
  const span = maxP - minP || 1;
  const W = 920;
  const H = 240;
  const PAD_TOP = 8;
  const PAD_BOTTOM = 8;
  const innerH = H - PAD_TOP - PAD_BOTTOM;
  const candleW = W / candles.length;
  const bodyW = Math.max(candleW * 0.6, 1.5);

  const yOf = (price: number): number =>
    PAD_TOP + (1 - (price - minP) / span) * innerH;

  const closesPath = candles
    .map((k, i) => `${i === 0 ? "M" : "L"} ${i * candleW + candleW / 2} ${yOf(k.c)}`)
    .join(" ");

  const last = candles[candles.length - 1];
  const lastPrice = last.c;
  const yLabels = [maxP, minP + span * 0.75, minP + span * 0.5, minP + span * 0.25, minP].map(
    (v) => v.toFixed(2),
  );

  return (
    <section className="chart" aria-label="gráfico ticker">
      <div className="chart__head">
        <span className="chart__title">
          <b>{ticker}</b>
          <span style={{ color: "var(--t-55)" }}>
            {" 15m · "}
            <span style={{ color: "var(--t-80)" }}>{lastPrice.toFixed(2)}</span>
            {` · ${candles.length} velas`}
          </span>
        </span>
      </div>
      <div className="chart__canvas">
        <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none">
          <title>chart 15m</title>
          {/* grilla horizontal */}
          <g stroke="rgba(255,255,255,0.04)" strokeWidth="1">
            <line x1="0" y1={PAD_TOP + innerH * 0.0} x2={W} y2={PAD_TOP + innerH * 0.0} />
            <line x1="0" y1={PAD_TOP + innerH * 0.25} x2={W} y2={PAD_TOP + innerH * 0.25} />
            <line x1="0" y1={PAD_TOP + innerH * 0.5} x2={W} y2={PAD_TOP + innerH * 0.5} />
            <line x1="0" y1={PAD_TOP + innerH * 0.75} x2={W} y2={PAD_TOP + innerH * 0.75} />
            <line x1="0" y1={PAD_TOP + innerH * 1.0} x2={W} y2={PAD_TOP + innerH * 1.0} />
          </g>
          {/* candles */}
          <g>
            {candles.map((k, i) => {
              const cx = i * candleW + candleW / 2;
              const yHi = yOf(k.h);
              const yLo = yOf(k.l);
              const yOpen = yOf(k.o);
              const yClose = yOf(k.c);
              const bullish = k.c >= k.o;
              const stroke = bullish ? "rgba(86,205,160,0.8)" : "rgba(232,93,93,0.8)";
              const fill = bullish ? "rgba(86,205,160,0.45)" : "rgba(232,93,93,0.45)";
              const bodyTop = Math.min(yOpen, yClose);
              const bodyH = Math.max(Math.abs(yClose - yOpen), 1);
              return (
                <g key={k.dt}>
                  <line x1={cx} x2={cx} y1={yHi} y2={yLo} stroke={stroke} strokeWidth="1" />
                  <rect
                    x={cx - bodyW / 2}
                    y={bodyTop}
                    width={bodyW}
                    height={bodyH}
                    fill={fill}
                    stroke={stroke}
                    strokeWidth="0.8"
                  />
                </g>
              );
            })}
          </g>
          {/* línea de cierres */}
          <path d={closesPath} fill="none" stroke="rgba(255,180,80,0.5)" strokeWidth="1.2" />
        </svg>
        <div className="chart__yaxis">
          {yLabels.map((p) => (
            <span key={p}>{p}</span>
          ))}
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
