import { useToast } from "@/components/Toast/ToastProvider";
import { CHAT_FORMAT_FALLBACK } from "@/lib/chatFormat";
import { copyToClipboard } from "@/lib/copyToClipboard";
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
   Lee el slot efectivo desde useEffectiveSlot (backend si hay, fallback
   del Hi-Fi v2 si no) — así cambia con cada selección de la watchlist
   incluso sin backend conectado. */
export function Panel({ cockpitState = "normal", ticker = null }: PanelProps) {
  const [detailOpen, setDetailOpen] = useState(false);

  return (
    <section className="panel" aria-label="detalle">
      <StateToasts state={cockpitState} ticker={ticker} />
      <Banner />
      <Exec />
      <Chart />
      <Detail open={detailOpen} onToggle={() => setDetailOpen((v) => !v)} />
    </section>
  );
}

function Banner() {
  const toast = useToast();
  const [copied, setCopied] = useState(false);
  const selectedId = useSlotsStore((s) => s.selectedSlotId);
  const effective = useEffectiveSlot(selectedId);
  const signal = useSignalsStore((s) => s.bySlot[selectedId]);

  const ticker = effective.ticker ?? "—";
  const band = effective.band ?? "B";
  const dir = effective.direction;
  const score = effective.score ?? 0;
  const label = signal?.signal ?? "SETUP";
  const slotIdStr = String(selectedId).padStart(2, "0");
  const fixtureId = effective.fixtureId ?? "—";

  const chatText = signal?.chat_format ?? CHAT_FORMAT_FALLBACK;

  const handleCopy = async () => {
    if (!effective.ticker) {
      toast.push("slot vacío — nada que copiar", "warn");
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

  // Slot vacío — mostramos un banner placeholder con texto neutro.
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

  return (
    // data-band activo del slot mostrado — alimenta el halo cromático del ticker
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
            <span>fixture {fixtureId === "—" ? `${ticker.toLowerCase()}_v5_2_0` : fixtureId}</span>
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

function Exec() {
  return (
    <section className="exec" aria-label="resumen ejecutivo">
      <div className="exec__grid">
        <div className="exec__price">
          <div className="exec__price-label">último</div>
          <div className="exec__price-num">$485.32</div>
          <div className="exec__price-chg">+0.82% · +$3.96</div>
        </div>
        <div className="exec__chips">
          <Chip label="alineación">
            <span className="pos">3/3 bullish</span> <span className="dim">15M·1H·D</span>
          </Chip>
          <Chip label="atr 15M">
            0.74% <span className="dim">($3.59)</span>
          </Chip>
          <Chip label="vela">
            14:30 ET <span className="dim">· calc +4s</span>
          </Chip>
          <Chip label="resistencias">
            $487.20 <span className="dim">PD</span> · $489.50 <span className="dim">R1</span>
          </Chip>
          <Chip label="soportes">
            $483.80 <span className="dim">S1</span> · $481.10 <span className="dim">PD</span>
          </Chip>
          <Chip label="vol mediana 15M">
            1.8× <span className="dim">·</span> <span className="accent">vela 2.1×</span>{" "}
            <span className="dim">(0.66)</span>
          </Chip>
        </div>
      </div>
    </section>
  );
}

function Chip({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="chip">
      <span className="chip__label">{label}</span>
      <span className="chip__val">{children}</span>
    </div>
  );
}

function Chart() {
  return (
    <section className="chart" aria-label="gráfico ticker">
      <div className="chart__head">
        <span className="chart__title">
          <b>QQQ · 15M</b>
          <span style={{ color: "var(--t-38)" }}>últimas 30 velas</span>
        </span>
        <span className="chart__legend">
          <span className="ma20">
            <i />
            MA20
          </span>
          <span className="ma40">
            <i />
            MA40
          </span>
          <span className="ma200">
            <i />
            MA200
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
          <path
            d="M10,180 L40,178 L70,176 L100,174 L130,172 L160,170 L190,168 L220,166 L250,164 L280,162 L310,160 L340,158 L370,156 L400,154 L430,152 L460,150 L490,148 L520,146 L550,144 L580,142 L610,140 L640,138 L670,136 L700,134 L730,132 L760,130 L790,128 L820,126 L850,124 L880,122 L910,120"
            fill="none"
            stroke="rgba(245,245,247,0.45)"
            strokeWidth="1.2"
          />
          <path
            d="M10,140 L40,138 L70,135 L100,132 L130,130 L160,128 L190,125 L220,122 L250,120 L280,118 L310,115 L340,112 L370,110 L400,108 L430,105 L460,102 L490,100 L520,97 L550,95 L580,92 L610,90 L640,88 L670,85 L700,82 L730,80 L760,78 L790,75 L820,72 L850,70 L880,68 L910,65"
            fill="none"
            stroke="#60a5fa"
            strokeWidth="1.4"
            opacity="0.75"
          />
          <path
            d="M10,120 L40,116 L70,112 L100,108 L130,105 L160,102 L190,98 L220,94 L250,90 L280,86 L310,82 L340,78 L370,75 L400,72 L430,68 L460,64 L490,60 L520,57 L550,54 L580,52 L610,50 L640,48 L670,46 L700,44 L730,42 L760,40 L790,38 L820,36 L850,34 L880,32 L910,30"
            fill="none"
            stroke="#FF6A2C"
            strokeWidth="1.6"
          />
        </svg>
        <div className="chart__yaxis">
          <span>$489.50</span>
          <span>$487.20</span>
          <span>$485.32</span>
          <span>$483.80</span>
          <span>$481.10</span>
        </div>
      </div>
      <a
        className="chart__open"
        href="https://www.tradingview.com/symbols/NASDAQ-QQQ/"
        target="_blank"
        rel="noopener noreferrer"
      >
        abrir en tradingview
      </a>
    </section>
  );
}

interface DetailProps {
  open: boolean;
  onToggle: () => void;
}

function Detail({ open, onToggle }: DetailProps) {
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
        <span className="detail__block-label">precio</span>
        <span className="detail__block-content">
          <span>
            <span className="k">último</span> <span className="v">$485.32</span>
          </span>
          <span>
            <span className="k">chg día</span> <span className="pos">+0.82%</span>
          </span>
          <span>
            <span className="k">ATR 15M</span> <span className="v">0.74%</span>{" "}
            <span className="dim">($3.59)</span>
          </span>
          <span>
            <span className="k">dMA200</span> <span className="pos">+3.2%</span>{" "}
            <span className="dim">($470.12)</span>
          </span>
        </span>

        <span className="detail__block-label">contexto</span>
        <span className="detail__block-content">
          <span>
            <span className="k">align</span> <span className="pos">3/3</span>{" "}
            <span className="dim">15M:bull · 1H:bull · D:bull</span>
          </span>
          <span>
            <span className="k">MAs D</span> <span className="v">20=$483 · 40=$478 · 200=$470</span>
          </span>
          <span>
            <span className="k">BB 1H</span> <span className="v">$482.10 / $484.50 / $486.90</span>
          </span>
        </span>

        <span className="detail__block-label">volumen</span>
        <span className="detail__block-content">
          <span>
            <span className="k">15M</span> <span className="v">1.8×</span>{" "}
            <span className="dim">mediana día</span>
          </span>
          <span>
            <span className="k">1H</span> <span className="v">1.4×</span>
          </span>
          <span>
            <span className="k">vela curso</span> <span className="v">2.1×</span>{" "}
            <span className="dim">proyectado (frac 0.66)</span>
          </span>
          <span>
            <span className="k">secuencia</span> <span className="pos">↑ creciente</span>
          </span>
        </span>

        <span className="detail__block-label">fuerza relativa</span>
        <span className="detail__block-content">
          <span>
            <span className="k">vs SPY</span> <span className="pos">+0.87%</span>
          </span>
          <span>
            <span className="k">DivSPY</span> <span className="v">QQQ +0.82% · SPY +0.41%</span>
          </span>
        </span>

        <span className="detail__block-label">niveles</span>
        <span className="detail__block-content">
          <span>
            <span className="k">R</span> <span className="v">$487.20</span>{" "}
            <span className="dim">(PD)</span>
          </span>
          <span>
            <span className="v">$489.50</span> <span className="dim">(R1)</span>
          </span>
          <span>
            <span className="k">S</span> <span className="v">$483.80</span>{" "}
            <span className="dim">(S1)</span>
          </span>
          <span>
            <span className="v">$481.10</span> <span className="dim">(PD)</span>
          </span>
        </span>

        <span className="detail__block-label">eventos</span>
        <span className="detail__block-content">
          <span>
            <span className="warn">⚡</span> <span className="v">Squeeze BB 1H</span>{" "}
            <span className="dim">ancho p12 → expansión</span>
          </span>
          <span>
            <span className="check">↑</span> <span className="v">ORB Breakout</span>{" "}
            <span className="dim">rango $484.10–$485.80</span>
          </span>
          <span>
            <span className="warn">⚠</span> <span className="v">Catalizador</span>{" "}
            <span className="dim">chg &gt; 1.5× ATR</span>
          </span>
        </span>

        <span className="detail__block-label">
          patrones{" "}
          <span
            style={{
              color: "var(--t-38)",
              fontFamily: "var(--font-mono)",
              fontSize: "9.5px",
            }}
          >
            (3)
          </span>
        </span>
        <span className="detail__block-content">
          <span className="pat">
            <span className="pname">Doji BB inf</span>
            <span className="pmeta">15M · bull · trigger · w:2</span>
          </span>
          <span className="pat">
            <span className="pname">ORB Breakout</span>
            <span className="pmeta">15M · bull · trigger · w:2</span>
          </span>
          <span className="pat">
            <span className="pname">BBinf_1H</span>
            <span className="pmeta">1H · bull · confirm · w:3</span>
          </span>
        </span>

        <span className="detail__block-label">scoring</span>
        <span className="detail__block-content">
          <span>
            <span className="k">estructura</span> <span className="check">✓</span>
          </span>
          <span>
            <span className="k">triggers</span> <span className="v">2</span>{" "}
            <span className="dim">(suma 4.0)</span>
          </span>
          <span>
            <span className="k">confirms</span> <span className="v">1</span>{" "}
            <span className="dim">(suma 3.0) tras dedup</span>
          </span>
          <span>
            <span className="k">bloqueo</span> <span className="dim">—</span>
          </span>
          <span>
            <span className="k">conflicto</span> <span className="dim">—</span>
          </span>
        </span>

        <div className="detail__sep" />

        <div className="detail__result">
          <span className="detail__result-label">resultado</span>
          <span className="detail__result-val">
            <span className="big">12.0</span>
            <span style={{ color: "var(--bull)", marginRight: 14 }}>CALL</span>
            <span style={{ color: "var(--band-aplus)", marginRight: 14 }}>A+</span>
            <span style={{ color: "var(--accent)" }}>SETUP</span>
          </span>
        </div>

        <span className="detail__block-label">meta</span>
        <span className="detail__block-content">
          <span>
            <span className="k">engine</span> <span className="v">5.2.0</span>
          </span>
          <span>
            <span className="k">fixture</span> <span className="v">qqq_v5_2_0</span>{" "}
            <span className="dim">v5.2.0</span>
          </span>
          <span>
            <span className="k">slot</span> <span className="v">02</span>
          </span>
          <span>
            <span className="k">vela</span> <span className="v">2026-04-25 14:30 ET</span>
          </span>
          <span>
            <span className="k">calc</span> <span className="v">2026-04-25 14:30:04 ET</span>
          </span>
        </span>
      </div>
    </section>
  );
}
