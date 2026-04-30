import type { ApiError } from "@/api/client";
import { useConfigCurrent, usePutTdKeys, useValidatorConnectivity } from "@/api/queries";
import type { TDKeyConfig } from "@/api/types";
import { useToast } from "@/components/Toast/ToastProvider";
import { Badge } from "@/components/ui/Badge";
import { useApiUsageStore } from "@/stores/apiUsage";
import { type ReactElement, useState } from "react";
import { Box, type BoxState } from "../Box";

/* Box 3 — Proveedor de datos · TwelveData (5 keys round-robin).

   Las keys vienen del .config runtime (`useConfigCurrent` →
   `cfg.twelvedata_keys`). El uso minuto/día llega live por WS
   `api_usage.tick` → store `useApiUsageStore`.

   Acciones v1:
   - Botón global "probar todas" → POST /validator/connectivity
     y mappea el response por `key_id` para mostrar ok/fail por card.
   - Botón global "agregar key" → form inline mínimo (alias + secret).
   - Botón × por card → quita la key del runtime via PUT.

   Edición fina (cambio de cred/min/día) queda como deuda — se hace
   editando el .config y volviendo a cargar. */

interface ProbeResult {
  ok: boolean;
  error?: string;
}

function emptyKey(): TDKeyConfig {
  return {
    key_id: "",
    secret: "",
    credits_per_minute: 8,
    credits_per_day: 800,
    enabled: true,
  };
}

export function Box3Keys(): ReactElement {
  const current = useConfigCurrent();
  const usage = useApiUsageStore((s) => s.keys);
  const probe = useValidatorConnectivity();
  const putKeys = usePutTdKeys();
  const { push: toast } = useToast();

  const [adding, setAdding] = useState(false);
  const [draft, setDraft] = useState<TDKeyConfig>(emptyKey());
  const [probeResults, setProbeResults] = useState<Record<string, ProbeResult>>({});
  const [probingId, setProbingId] = useState<string | null>(null);

  const cfg = current.data?.config;
  const keys = cfg?.twelvedata_keys ?? [];

  const probedOk = Object.values(probeResults).filter((r) => r.ok).length;
  const probedTotal = Object.keys(probeResults).length;

  // Semáforo (UX-001):
  // - rojo si 0 keys configuradas (no funciona el data engine).
  // - verde si ≥1 key configurada y al menos 1 probada OK (1 sola es suficiente).
  // - verde si ≥1 key configurada y nunca se probó (asumimos OK hasta probar).
  // - warn si todas las keys probadas fallaron (TODO probaron y NINGUNA OK).
  // - warn si al menos una falló pero alguna OK (parcial).
  let state: BoxState;
  if (keys.length === 0) state = "err";
  else if (probedTotal === 0)
    state = "ok"; // sin probar pero configurado
  else if (probedOk === 0)
    state = "err"; // todas las probadas fallaron
  else if (probedOk < probedTotal)
    state = "warn"; // parcial
  else state = "ok"; // ≥1 OK

  const statusText =
    keys.length === 0
      ? "0 keys"
      : probedTotal === 0
        ? `${keys.length} / 5 · sin probar`
        : `${probedOk} / ${probedTotal} ok`;

  const errMsg = (e: unknown): string => {
    const err = e as ApiError;
    return typeof err.body === "string"
      ? err.body
      : err.body
        ? JSON.stringify(err.body)
        : err.message;
  };

  const onProbeAll = async () => {
    try {
      const r = await probe.mutateAsync();
      const results: Record<string, ProbeResult> = {};
      for (const k of r.td_keys) {
        results[k.key_id] = { ok: k.ok, error: k.error };
      }
      setProbeResults(results);
      const okN = r.td_keys.filter((k) => k.ok).length;
      toast(
        `probe completo · ${okN}/${r.td_keys.length} ok`,
        okN === r.td_keys.length ? "success" : "warn",
      );
    } catch (e) {
      toast(`probe falló — ${errMsg(e)}`, "error");
    }
  };

  const onProbeOne = async (keyId: string) => {
    setProbingId(keyId);
    try {
      const r = await probe.mutateAsync();
      const found = r.td_keys.find((k) => k.key_id === keyId);
      if (found) {
        setProbeResults((prev) => ({ ...prev, [keyId]: { ok: found.ok, error: found.error } }));
        toast(
          `${keyId} · ${found.ok ? "ok" : `fail · ${found.error ?? "?"}`}`,
          found.ok ? "success" : "error",
        );
      }
    } catch (e) {
      toast(`probe falló — ${errMsg(e)}`, "error");
    } finally {
      setProbingId(null);
    }
  };

  const onRemove = async (keyId: string) => {
    const next = keys.filter((k) => k.key_id !== keyId);
    try {
      await putKeys.mutateAsync({ keys: next });
      toast(`${keyId} eliminada`, "info");
      setProbeResults((prev) => {
        const { [keyId]: _, ...rest } = prev;
        return rest;
      });
    } catch (e) {
      toast(`no se pudo eliminar — ${errMsg(e)}`, "error");
    }
  };

  const onAdd = async () => {
    if (!draft.key_id.trim() || !draft.secret.trim()) {
      toast("ingresá key_id y secret", "warn");
      return;
    }
    if (keys.some((k) => k.key_id === draft.key_id.trim())) {
      toast("ya existe una key con ese key_id", "warn");
      return;
    }
    if (keys.length >= 5) {
      toast("máximo 5 keys", "warn");
      return;
    }
    const next = [...keys, { ...draft, key_id: draft.key_id.trim(), secret: draft.secret.trim() }];
    try {
      await putKeys.mutateAsync({ keys: next });
      toast(`${draft.key_id} agregada`, "success");
      setDraft(emptyKey());
      setAdding(false);
    } catch (e) {
      toast(`no se pudo agregar — ${errMsg(e)}`, "error");
    }
  };

  const slots = Array.from({ length: 5 }, (_, i) => keys[i] ?? null);

  return (
    <Box
      id={3}
      state={state}
      title="Proveedor de datos · TwelveData"
      sub={
        <>
          5 keys round-robin · KeyPool · probe individual + agregado · uso live via WS{" "}
          <span className="ref">api_usage.tick</span>
        </>
      }
      statusText={statusText}
    >
      <div className="toolbar">
        <span className="toolbar__left">
          <span className="ref">probar todas</span> usa{" "}
          <span className="ref">/validator/connectivity</span> · check G
        </span>
        <div className="toolbar__right">
          <button
            type="button"
            className="btn"
            onClick={onProbeAll}
            disabled={probe.isPending || keys.length === 0}
          >
            {probe.isPending ? "probando…" : "probar todas"}
          </button>
          <button
            type="button"
            className="btn is-primary"
            onClick={() => setAdding((a) => !a)}
            disabled={keys.length >= 5}
          >
            {adding ? "cancelar" : "+ agregar key"}
          </button>
        </div>
      </div>

      {adding ? (
        <div
          className="card"
          style={{ marginBottom: "var(--gap-4)", borderColor: "rgba(255,106,44,0.32)" }}
        >
          <div className="card__title">Nueva key</div>
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "1fr 1fr 100px 110px",
              gap: "10px",
              marginTop: "10px",
            }}
          >
            <div className="field">
              <label htmlFor="td-new-id">key_id</label>
              <input
                id="td-new-id"
                className="inp"
                type="text"
                value={draft.key_id}
                onChange={(e) => setDraft({ ...draft, key_id: e.target.value })}
                placeholder="key 1"
              />
            </div>
            <div className="field">
              <label htmlFor="td-new-secret">secret</label>
              <input
                id="td-new-secret"
                className="inp"
                type="password"
                value={draft.secret}
                onChange={(e) => setDraft({ ...draft, secret: e.target.value })}
                placeholder="API key…"
              />
            </div>
            <div className="field">
              <label htmlFor="td-new-cpm">cred / min</label>
              <input
                id="td-new-cpm"
                className="inp"
                type="number"
                min={1}
                value={draft.credits_per_minute}
                onChange={(e) =>
                  setDraft({
                    ...draft,
                    credits_per_minute: Number.parseInt(e.target.value, 10) || 1,
                  })
                }
              />
            </div>
            <div className="field">
              <label htmlFor="td-new-cpd">cred / día</label>
              <input
                id="td-new-cpd"
                className="inp"
                type="number"
                min={1}
                value={draft.credits_per_day}
                onChange={(e) =>
                  setDraft({ ...draft, credits_per_day: Number.parseInt(e.target.value, 10) || 1 })
                }
              />
            </div>
          </div>
          <div
            style={{ marginTop: "10px", display: "flex", gap: "8px", justifyContent: "flex-end" }}
          >
            <button type="button" className="btn is-ghost" onClick={() => setAdding(false)}>
              cancelar
            </button>
            <button
              type="button"
              className="btn is-primary"
              onClick={onAdd}
              disabled={putKeys.isPending}
            >
              {putKeys.isPending ? "guardando…" : "agregar"}
            </button>
          </div>
        </div>
      ) : null}

      <div className="keys-grid">
        {slots.map((k, idx) => {
          if (!k) {
            return (
              <button
                type="button"
                // biome-ignore lint/suspicious/noArrayIndexKey: el slot vacío representa una posición fija (1..5) sin ID propio.
                key={`empty-${idx}`}
                className="key-card is-empty"
                onClick={() => setAdding(true)}
              >
                <div className="key-card__empty-icon">+</div>
                <div className="key-card__empty-text">slot {idx + 1}</div>
                <div className="dropzone__sub" style={{ fontSize: "9px" }}>
                  agregar key
                </div>
              </button>
            );
          }
          const u = usage[k.key_id];
          const pr = probeResults[k.key_id];
          const probing = probingId === k.key_id || (probe.isPending && !probingId);
          const cardState: BoxState = !pr ? "ok" : pr.ok ? "ok" : "err";
          const cls = cardState === "ok" ? "key-card" : `key-card is-${cardState}`;
          return (
            <div key={k.key_id} className={cls}>
              <div className="key-card__head">
                <div className="key-card__alias">{k.key_id}</div>
                <div style={{ display: "inline-flex", alignItems: "center", gap: "6px" }}>
                  {probing ? (
                    <Badge variant="run">⟳ probando</Badge>
                  ) : pr ? (
                    pr.ok ? (
                      <Badge variant="ok">ok</Badge>
                    ) : (
                      <Badge variant="err">fail</Badge>
                    )
                  ) : (
                    <Badge variant="pend">no probada</Badge>
                  )}
                  <button
                    type="button"
                    className="key-card__rmv"
                    onClick={() => onRemove(k.key_id)}
                    aria-label={`eliminar ${k.key_id}`}
                  >
                    ×
                  </button>
                </div>
              </div>
              <div className="field">
                <span className="field-lbl">secret</span>
                <div className="inp is-masked">••••••••••••••••</div>
              </div>
              <div className="key-card__cred">
                <div className="field">
                  <span className="field-lbl">cred / min</span>
                  <div className="inp">{k.credits_per_minute}</div>
                </div>
                <div className="field">
                  <span className="field-lbl">cred / día</span>
                  <div className="inp">{k.credits_per_day}</div>
                </div>
              </div>
              <button
                type="button"
                className="btn is-ghost sm"
                onClick={() => onProbeOne(k.key_id)}
                disabled={probe.isPending}
              >
                {probing ? "probando…" : "probar"}
              </button>
              <div className="key-card__live">
                {u ? (
                  <>
                    <div className="row">
                      <span>uso minuto</span>
                      <span className="num">
                        {u.used_minute} / {u.max_minute}
                      </span>
                    </div>
                    <div className="pg">
                      <i style={{ width: `${(u.used_minute / u.max_minute) * 100}%` }} />
                    </div>
                    <div className="row">
                      <span>uso diario</span>
                      <span className="num">
                        {u.used_daily} / {u.max_daily}
                      </span>
                    </div>
                    <div className="pg">
                      <i style={{ width: `${(u.used_daily / u.max_daily) * 100}%` }} />
                    </div>
                    {u.last_call_ts ? (
                      <div className="row">
                        <span>último call</span>
                        <span className="num">{new Date(u.last_call_ts).toLocaleTimeString()}</span>
                      </div>
                    ) : null}
                  </>
                ) : pr && !pr.ok ? (
                  <div className="err-msg">{pr.error ?? "fail"}</div>
                ) : (
                  <div className="row">
                    <span>esperando uso…</span>
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>

      <div className="note" style={{ marginTop: "var(--gap-4)" }}>
        las cards leen las keys del <span className="accent">.config</span> runtime · el uso por
        minuto / día llega via WS <span className="accent">api_usage.tick</span> al cierre de cada
        ciclo 15M · el agregado total también se refleja en el apibar del Cockpit
      </div>
    </Box>
  );
}
