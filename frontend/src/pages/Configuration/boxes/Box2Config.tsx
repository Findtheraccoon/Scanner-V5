import type { ApiError } from "@/api/client";
import {
  useConfigClear,
  useConfigCurrent,
  useConfigLast,
  useConfigLoad,
  useConfigSave,
  useConfigSaveAs,
} from "@/api/queries";
import { useToast } from "@/components/Toast/ToastProvider";
import { type ReactElement, useState } from "react";
import { Box, type BoxState } from "../Box";

/* Box 2 — Archivo de configuración (.config plaintext).

   Modelo: el `.config` es un archivo portable que el usuario maneja
   como un documento (Cargar / Guardar / Descargar / Limpiar). El
   sistema persiste sólo el path del último cargado en
   `data/last_config_path.json` para el "Auto-LAST".

   Card izquierda · acciones:
   - Path actual + path del LAST.
   - Input para cargar `.config` por path absoluto (decisión: el
     backend corre local junto al frontend).
   - Botones: cargar · guardar · guardar como · descargar · limpiar.

   Card derecha · resumen del contenido:
   - twelvedata_keys count · tickers asignados · fixtures · prefs · S3.
   - Aviso sobre bearer (vive sólo en localStorage, no se persiste). */

function pathBasename(p: string | null | undefined): string {
  if (!p) return "—";
  const parts = p.split(/[\\/]+/);
  return parts[parts.length - 1] || p;
}

function downloadJson(filename: string, payload: unknown): void {
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

export function Box2Config(): ReactElement {
  const current = useConfigCurrent();
  const last = useConfigLast();
  const load = useConfigLoad();
  const save = useConfigSave();
  const saveAs = useConfigSaveAs();
  const clear = useConfigClear();
  const { push: toast } = useToast();

  const [pathInput, setPathInput] = useState("");
  const [saveAsPath, setSaveAsPath] = useState("");

  const loaded = current.data?.loaded ?? false;
  const cfg = current.data?.config ?? null;
  const currentPath = current.data?.path ?? null;

  // Semáforo (UX-001): rojo si no hay .config cargado · verde si sí.
  const state: BoxState = loaded ? "ok" : "err";
  const statusText = loaded ? "cargado" : "sin cargar";

  const errMsg = (e: unknown): string => {
    const err = e as ApiError;
    return typeof err.body === "string"
      ? err.body
      : err.body
        ? JSON.stringify(err.body)
        : err.message;
  };

  const onLoad = async () => {
    if (!pathInput.trim()) {
      toast("ingresá un path absoluto del .config", "warn");
      return;
    }
    try {
      const r = await load.mutateAsync({ path: pathInput.trim() });
      toast(`cargado: ${r.name}`, "success");
      setPathInput("");
    } catch (e) {
      toast(`no se pudo cargar — ${errMsg(e)}`, "error");
    }
  };

  const onSave = async () => {
    try {
      const r = await save.mutateAsync({});
      toast(`guardado en ${r.path}`, "success");
    } catch (e) {
      toast(`no se pudo guardar — ${errMsg(e)}`, "error");
    }
  };

  const onSaveAs = async () => {
    if (!saveAsPath.trim()) {
      toast("ingresá un path para 'guardar como'", "warn");
      return;
    }
    try {
      const r = await saveAs.mutateAsync({ path: saveAsPath.trim() });
      toast(`guardado como ${r.path}`, "success");
      setSaveAsPath("");
    } catch (e) {
      toast(`no se pudo guardar como — ${errMsg(e)}`, "error");
    }
  };

  const onDownload = () => {
    if (!cfg) {
      toast("no hay config cargado para descargar", "warn");
      return;
    }
    const filename = `${cfg.name || "config"}.json`;
    downloadJson(filename, cfg);
    toast(`descargado ${filename}`, "info");
  };

  const onClear = async () => {
    if (!loaded) return;
    try {
      await clear.mutateAsync();
      toast("config limpiado del runtime", "info");
    } catch (e) {
      toast(`no se pudo limpiar — ${errMsg(e)}`, "error");
    }
  };

  const tickers = cfg ? ((cfg.preferences?.tickers as string[] | undefined) ?? []) : [];
  const fixtureCount = cfg
    ? Object.keys((cfg.preferences?.fixture_path_by_slot as Record<string, string>) ?? {}).length
    : 0;
  const tdKeysCount = cfg?.twelvedata_keys.length ?? 0;
  const s3Configured = cfg?.s3_config != null;

  return (
    <Box
      id={2}
      state={state}
      title="Archivo de configuración"
      sub={
        <>
          plaintext (sin encripción) · contiene TD keys + fixtures + preferencias · si no se carga
          un <span className="ref">.config</span>, el sistema arranca de cero
        </>
      }
      statusText={statusText}
    >
      <div className="cfg-wrap">
        <div className="card">
          <div className="card__title">Archivo activo</div>
          <div className="card__sub">en runtime los secretos viven en memoria</div>

          <div className="cfg-active">
            <span className="cfg-active__name">{pathBasename(currentPath)}</span>
            {!loaded ? <span className="badge is-pend">sin cargar</span> : null}
          </div>

          <div className="field" style={{ marginTop: "12px" }}>
            <label htmlFor="cfg-load-path">Cargar otro · path absoluto</label>
            <input
              id="cfg-load-path"
              className="inp"
              type="text"
              placeholder="/ruta/al/config.json"
              value={pathInput}
              onChange={(e) => setPathInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") onLoad();
              }}
            />
          </div>

          <div className="cfg-actions">
            <button
              type="button"
              className="btn"
              onClick={onLoad}
              disabled={load.isPending || !pathInput.trim()}
            >
              {load.isPending ? "cargando…" : "cargar"}
            </button>
            <button
              type="button"
              className="btn is-primary"
              onClick={onSave}
              disabled={save.isPending || !loaded || !currentPath}
            >
              {save.isPending ? "guardando…" : "guardar"}
            </button>
            <button type="button" className="btn" onClick={onDownload} disabled={!cfg}>
              descargar
            </button>
            <button
              type="button"
              className="btn is-ghost is-danger"
              onClick={onClear}
              disabled={!loaded || clear.isPending}
            >
              {clear.isPending ? "limpiando…" : "limpiar runtime"}
            </button>
          </div>

          <div className="field" style={{ marginTop: "12px" }}>
            <label htmlFor="cfg-saveas-path">Guardar como · path nuevo</label>
            <div style={{ display: "flex", gap: "8px" }}>
              <input
                id="cfg-saveas-path"
                className="inp"
                type="text"
                placeholder="/ruta/al/nuevo.json"
                value={saveAsPath}
                onChange={(e) => setSaveAsPath(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") onSaveAs();
                }}
                style={{ flex: 1 }}
              />
              <button
                type="button"
                className="btn"
                onClick={onSaveAs}
                disabled={saveAs.isPending || !cfg || !saveAsPath.trim()}
              >
                {saveAs.isPending ? "…" : "guardar como"}
              </button>
            </div>
          </div>

          <div className="note" style={{ marginTop: "14px" }}>
            <span className="accent">guardar</span> sobreescribe el archivo activo ·{" "}
            <span className="accent">descargar</span> exporta el estado actual a un .json en tu
            navegador
          </div>
        </div>

        <div className="card">
          <div className="card__title">Contenido del archivo</div>
          <div className="card__sub">qué entra al guardar · qué sale al cargar</div>

          <div className="cfg-state" style={{ marginTop: "12px" }}>
            <div className="cfg-state__row">
              <span className="lbl">twelvedata keys</span>
              <span className="val">{tdKeysCount === 0 ? "—" : `${tdKeysCount} / 5 keys`}</span>
            </div>
            <div className="cfg-state__row">
              <span className="lbl">tickers asignados</span>
              <span className="val">{tickers.length === 0 ? "—" : tickers.join(" · ")}</span>
            </div>
            <div className="cfg-state__row">
              <span className="lbl">fixtures por slot</span>
              <span className="val">{fixtureCount === 0 ? "—" : `${fixtureCount} fixtures`}</span>
            </div>
            <div className="cfg-state__row">
              <span className="lbl">backup S3</span>
              <span className={`val ${s3Configured ? "is-ok" : "is-pend"}`}>
                {s3Configured ? "configurado" : "no configurado"}
              </span>
            </div>
            <div className="cfg-state__divider" />
            <div className="cfg-state__row">
              <span className="lbl" style={{ color: "var(--warn)" }}>
                no se persiste
              </span>
              <span className="val is-warn">bearer token (vive sólo en localStorage)</span>
            </div>
          </div>

          <div className="note" style={{ marginTop: "14px" }}>
            último <span className="accent">.config</span> usado:{" "}
            <span className="num">{last.data?.path ?? "—"}</span>
            {last.data?.loaded_at ? (
              <>
                <br />
                {new Date(last.data.loaded_at).toLocaleString()}
              </>
            ) : null}
          </div>
        </div>
      </div>
    </Box>
  );
}
