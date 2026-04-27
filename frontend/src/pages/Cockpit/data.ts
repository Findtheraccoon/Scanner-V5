/* Datos hardcoded extraídos del Hi-Fi v2.
   Reemplazables por el backend (REST + WS) en iteraciones siguientes.
   Mantienen el rendering 1:1 con frontend/wireframing/Cockpit Hi-Fi v2.html. */

export type Band = "REVISAR" | "B" | "A" | "A+" | "S" | "S+";
export type Direction = "CALL" | "PUT" | "—";

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
  band: Band | null;
  direction: Direction;
  score: number | null;
  winRate: number | null;
  selected: boolean;
  metallic: boolean;
  sparkline: SparklineGradient | null;
}

export const SLOTS: SlotData[] = [
  {
    id: 1,
    ticker: "SPY",
    band: "A",
    direction: "CALL",
    score: 9.0,
    winRate: 61,
    selected: false,
    metallic: false,
    sparkline: {
      id: "sg1",
      fillStops: [
        { offset: "0%", color: "#FF6A2C", opacity: 0.55 },
        { offset: "100%", color: "#FF6A2C", opacity: 0 },
      ],
      strokeStops: [
        { offset: "0%", color: "#FF6A2C", opacity: 0.55 },
        { offset: "50%", color: "#FF6A2C", opacity: 1 },
        { offset: "100%", color: "#FFB088", opacity: 1 },
      ],
      fillPath:
        "M0,38 L20,36 L40,32 L60,34 L80,30 L100,26 L120,28 L140,22 L160,24 L180,18 L200,16 L220,20 L240,14 L260,12 L280,8 L300,6 L320,4 L320,50 L0,50 Z",
      strokePath:
        "M0,38 L20,36 L40,32 L60,34 L80,30 L100,26 L120,28 L140,22 L160,24 L180,18 L200,16 L220,20 L240,14 L260,12 L280,8 L300,6 L320,4",
      strokeWidth: 1.4,
    },
  },
  {
    id: 2,
    ticker: "QQQ",
    band: "A+",
    direction: "CALL",
    score: 12.0,
    winRate: 68,
    selected: true,
    metallic: false,
    sparkline: {
      id: "sg2",
      fillStops: [
        { offset: "0%", color: "#FF6A2C", opacity: 0.65 },
        { offset: "100%", color: "#FF6A2C", opacity: 0 },
      ],
      strokeStops: [
        { offset: "0%", color: "#FF6A2C", opacity: 0.6 },
        { offset: "50%", color: "#FF6A2C", opacity: 1 },
        { offset: "100%", color: "#FFB088", opacity: 1 },
      ],
      fillPath:
        "M0,42 L20,40 L40,37 L60,34 L80,36 L100,30 L120,28 L140,32 L160,26 L180,22 L200,18 L220,20 L240,14 L260,10 L280,8 L300,6 L320,4 L320,50 L0,50 Z",
      strokePath:
        "M0,42 L20,40 L40,37 L60,34 L80,36 L100,30 L120,28 L140,32 L160,26 L180,22 L200,18 L220,20 L240,14 L260,10 L280,8 L300,6 L320,4",
      strokeWidth: 1.6,
    },
  },
  {
    id: 3,
    ticker: "IWM",
    band: "S",
    direction: "CALL",
    score: 15.0,
    winRate: 71,
    selected: false,
    metallic: false,
    sparkline: {
      id: "sg3",
      fillStops: [
        { offset: "0%", color: "#DC9418", opacity: 0.55 },
        { offset: "100%", color: "#DC9418", opacity: 0 },
      ],
      strokeStops: [
        { offset: "0%", color: "#DC9418", opacity: 0.7 },
        { offset: "100%", color: "#FFD580", opacity: 1 },
      ],
      fillPath:
        "M0,44 L20,42 L40,38 L60,40 L80,34 L100,32 L120,28 L140,30 L160,24 L180,22 L200,18 L220,20 L240,14 L260,12 L280,10 L300,8 L320,6 L320,50 L0,50 Z",
      strokePath:
        "M0,44 L20,42 L40,38 L60,40 L80,34 L100,32 L120,28 L140,30 L160,24 L180,22 L200,18 L220,20 L240,14 L260,12 L280,10 L300,8 L320,6",
      strokeWidth: 1.5,
    },
  },
  {
    id: 4,
    ticker: "AAPL",
    band: "B",
    direction: "CALL",
    score: 6.0,
    winRate: 54,
    selected: false,
    metallic: false,
    sparkline: {
      id: "sg4",
      fillStops: [
        { offset: "0%", color: "#60a5fa", opacity: 0.5 },
        { offset: "100%", color: "#60a5fa", opacity: 0 },
      ],
      strokeStops: [
        { offset: "0%", color: "#3b82f6", opacity: 0.6 },
        { offset: "100%", color: "#bfdbfe", opacity: 1 },
      ],
      fillPath:
        "M0,32 L20,30 L40,34 L60,28 L80,30 L100,26 L120,28 L140,22 L160,24 L180,20 L200,22 L220,18 L240,20 L260,16 L280,18 L300,14 L320,12 L320,50 L0,50 Z",
      strokePath:
        "M0,32 L20,30 L40,34 L60,28 L80,30 L100,26 L120,28 L140,22 L160,24 L180,20 L200,22 L220,18 L240,20 L260,16 L280,18 L300,14 L320,12",
      strokeWidth: 1.4,
    },
  },
  {
    id: 5,
    ticker: "NVDA",
    band: "S+",
    direction: "CALL",
    score: 18.0,
    winRate: 76,
    selected: false,
    metallic: true,
    sparkline: {
      id: "sg5",
      fillStops: [
        { offset: "0%", color: "#f5f5f7", opacity: 0.55 },
        { offset: "100%", color: "#f5f5f7", opacity: 0 },
      ],
      strokeStops: [
        { offset: "0%", color: "#cbd5e1", opacity: 0.7 },
        { offset: "100%", color: "#ffffff", opacity: 1 },
      ],
      fillPath:
        "M0,46 L20,44 L40,40 L60,36 L80,30 L100,24 L120,20 L140,16 L160,12 L180,10 L200,8 L220,6 L240,4 L260,3 L280,3 L300,2 L320,2 L320,50 L0,50 Z",
      strokePath:
        "M0,46 L20,44 L40,40 L60,36 L80,30 L100,24 L120,20 L140,16 L160,12 L180,10 L200,8 L220,6 L240,4 L260,3 L280,3 L300,2 L320,2",
      strokeWidth: 1.6,
    },
  },
  {
    id: 6,
    ticker: null,
    band: null,
    direction: "—",
    score: null,
    winRate: null,
    selected: false,
    metallic: false,
    sparkline: null,
  },
];
