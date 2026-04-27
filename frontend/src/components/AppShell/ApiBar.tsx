interface KeyCellData {
  name: string;
  lastSeen: string;
  used: number;
  capacity: number;
}

interface DailyRowData {
  name: string;
  used: number;
  cap: number;
}

const KEYS: KeyCellData[] = [
  { name: "key 1", lastSeen: "hace 3s", used: 4, capacity: 8 },
  { name: "key 2", lastSeen: "hace 1s", used: 6, capacity: 8 },
  { name: "key 3", lastSeen: "hace 7s", used: 2, capacity: 8 },
  { name: "key 4", lastSeen: "hace 4s", used: 5, capacity: 8 },
  { name: "key 5", lastSeen: "hace 9s", used: 3, capacity: 8 },
];

const DAILY: DailyRowData[] = [
  { name: "key 1", used: 312, cap: 800 },
  { name: "key 2", used: 287, cap: 800 },
  { name: "key 3", used: 198, cap: 800 },
  { name: "key 4", used: 256, cap: 800 },
  { name: "key 5", used: 173, cap: 800 },
];

export function ApiBar() {
  return (
    <section className="apibar" aria-label="estado api">
      <div className="apibar__cell apibar__cell--controls">
        <button type="button" className="btn-scan" aria-label="ejecutar scan">
          <svg
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden="true"
          >
            <title>scan</title>
            <path d="M21 21l-4.35-4.35" />
            <circle cx="11" cy="11" r="7" />
          </svg>
          <span>scan ahora</span>
        </button>
        <div className="toggle is-on" aria-label="auto-scan toggle">
          <span className="toggle__label">auto</span>
          <span className="toggle__switch" />
          <span className="toggle__state">on</span>
        </div>
      </div>

      {KEYS.map((k) => (
        <div className="apibar__cell" key={k.name}>
          <div className="apibar__keyhead">
            <span className="apibar__keyname">{k.name}</span>
            <span className="apibar__keysep">·</span>
            <span className="apibar__keylast">{k.lastSeen}</span>
          </div>
          <div className="apibar__keyusage">
            {k.used}/{k.capacity}
          </div>
          <div className="apibar__bar">
            <i style={{ width: `${(k.used / k.capacity) * 100}%` }} />
          </div>
        </div>
      ))}

      <div className="apibar__cell">
        <div className="daily-stack">
          {DAILY.map((row) => (
            <div className="daily-row" key={row.name}>
              <span className="daily-row__name">{row.name}</span>
              <span className="daily-row__bar">
                <i style={{ width: `${(row.used / row.cap) * 100}%` }} />
              </span>
              <span className="daily-row__num">
                {row.used}
                <span className="dim">/{row.cap}</span>
              </span>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
