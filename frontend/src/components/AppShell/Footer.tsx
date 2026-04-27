import type { EngineStatusLevel } from "@/api/types";
import { useToast } from "@/components/Toast/ToastProvider";
import { useAuthStore } from "@/stores/auth";
import { useEngineStore } from "@/stores/engine";
import { useEffect, useId, useState } from "react";

const PILL_LABEL: Record<"data" | "scoring" | "database", string> = {
  scoring: "motor scoring",
  data: "data engine",
  database: "database",
};

function statusClass(status: EngineStatusLevel): string {
  if (status === "green") return "ok";
  if (status === "yellow") return "warn";
  if (status === "paused") return "warn";
  return "err";
}

export function Footer() {
  const engine = useEngineStore();
  const token = useAuthStore((s) => s.token);
  const setToken = useAuthStore((s) => s.setToken);
  const toast = useToast();
  const [draft, setDraft] = useState(token ?? "");
  const inputId = useId();

  useEffect(() => {
    setDraft(token ?? "");
  }, [token]);

  const handleSave = () => {
    const next = draft.trim() || null;
    setToken(next);
    if (next) toast.push("token guardado", "success");
    else toast.push("token borrado", "info");
  };

  return (
    <footer className="footer">
      <div className="footer__left">
        <span className="apibar__label">proveedor · twelvedata · 5 keys · round-robin</span>
      </div>
      <div className="footer__center">
        <label className="footer__token" htmlFor={inputId}>
          <span>bearer</span>
          <input
            id={inputId}
            type="password"
            placeholder={token ? "•••" : "token"}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") handleSave();
            }}
            autoComplete="off"
            spellCheck={false}
          />
          <button type="button" onClick={handleSave}>
            guardar
          </button>
        </label>
      </div>
      <div className="footer__right">
        <span className="footer__status">
          <span className={statusClass(engine.scoring)}>{PILL_LABEL.scoring}</span>
          <span className={statusClass(engine.data)}>
            {PILL_LABEL.data}
            {engine.dataPaused ? " · pause" : ""}
          </span>
          <span className={statusClass(engine.database)}>{PILL_LABEL.database}</span>
        </span>
      </div>
    </footer>
  );
}
