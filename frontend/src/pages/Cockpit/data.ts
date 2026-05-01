/* Tipos compartidos del Cockpit (Watchlist + Slot card + Sparkline).

   Antes este archivo contenía un fallback hardcoded del Hi-Fi v2 con
   SPY/QQQ/IWM/AAPL/NVDA + sparklines fijas. Se eliminó porque el
   Cockpit no debe mostrar fake data: lo que reporta el backend es lo
   único que pinta la UI. UX-003. */

import type { SignalConfidence, SignalDirection } from "@/api/types";

export interface SparklineGradient {
  id: string;
  fillStops: Array<{ offset: string; color: string; opacity: number }>;
  strokeStops: Array<{ offset: string; color: string; opacity: number }>;
  fillPath: string;
  strokePath: string;
  strokeWidth: number;
}

export interface SlotData {
  id: number;
  ticker: string | null;
  band: SignalConfidence | null;
  direction: SignalDirection | null;
  score: number | null;
  winRate: number | null;
  selected: boolean;
  metallic: boolean;
  sparkline: SparklineGradient | null;
}
