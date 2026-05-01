import type { ApiError } from "@/api/client";
import { useConfigCurrent, usePutS3, useS3Backup, useS3List, useS3Restore } from "@/api/queries";
import type { S3Config } from "@/api/types";
import { useToast } from "@/components/Toast/ToastProvider";
import { type ReactElement, useEffect, useState } from "react";
import { Box, type BoxState } from "../Box";

/* Box 6 — Backup remoto · S3-compatible.

   Sub-secciones:
   - Form de credenciales (endpoint_url · region · bucket · prefix ·
     access_key · secret_key) que se persiste en el .config via
     PUT /config/s3.
   - Listado de backups (POST /database/backups).
   - Acciones · probar conexión · backup ahora · restaurar.

   Hidrata el form al cargarse desde `cfg.s3_config` runtime.
   El restore tiene confirmación doble por su naturaleza destructiva. */

function emptyS3(): S3Config {
  return {
    endpoint_url: null,
    bucket: "",
    access_key_id: "",
    secret_access_key: "",
    region: "us-east-1",
    key_prefix: "scanner-backups/",
  };
}

function bytesPretty(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  if (n < 1024 * 1024 * 1024) return `${(n / 1024 / 1024).toFixed(1)} MB`;
  return `${(n / 1024 / 1024 / 1024).toFixed(2)} GB`;
}

export function Box6S3(): ReactElement {
  const cfg = useConfigCurrent(true); // include_secrets para hidratar el form
  const putS3 = usePutS3();
  const list = useS3List();
  const backupRun = useS3Backup();
  const restore = useS3Restore();
  const { push: toast } = useToast();

  const [form, setForm] = useState<S3Config>(emptyS3());
  const [hydrated, setHydrated] = useState(false);

  // Hidrata el form una vez cuando llega el config desde el backend.
  useEffect(() => {
    if (!hydrated && cfg.data?.config?.s3_config) {
      setForm(cfg.data.config.s3_config);
      setHydrated(true);
    }
  }, [cfg.data, hydrated]);

  const errMsg = (e: unknown): string => {
    const err = e as ApiError;
    return typeof err.body === "string"
      ? err.body
      : err.body
        ? JSON.stringify(err.body)
        : err.message;
  };

  const isConfigured = !!cfg.data?.config?.s3_config;
  const objects = list.data?.objects ?? [];

  // Semáforo (UX-001): S3 es OPCIONAL — sin configurar no es error.
  // - pend (gris) si no configurado nunca (estado por defecto, opcional).
  // - warn si configurado pero el último probe falló.
  // - ok si configurado y probe OK.
  let state: BoxState;
  if (!isConfigured) state = "pend";
  else if (list.isError) state = "warn";
  else state = "ok";

  const statusText = isConfigured
    ? list.isError
      ? "sin conexión"
      : objects.length > 0
        ? `${objects.length} backup${objects.length === 1 ? "" : "s"}`
        : "configurado"
    : "sin configurar";

  const isFormValid =
    form.bucket.trim().length > 0 &&
    form.access_key_id.trim().length > 0 &&
    form.secret_access_key.trim().length > 0;

  const onSaveCreds = async () => {
    if (!isFormValid) {
      toast("completá bucket, access key y secret key", "warn");
      return;
    }
    try {
      await putS3.mutateAsync({ s3: form });
      toast("credenciales S3 guardadas en runtime", "success");
    } catch (e) {
      toast(`no se pudo guardar — ${errMsg(e)}`, "error");
    }
  };

  const onTestConnection = async () => {
    if (!isFormValid) {
      toast("completá bucket, access key y secret key", "warn");
      return;
    }
    try {
      const r = await list.mutateAsync({ s3: form });
      toast(`conexión OK · ${r.objects.length} backups en el bucket`, "success");
    } catch (e) {
      toast(`probe falló — ${errMsg(e)}`, "error");
    }
  };

  const onBackupNow = async () => {
    if (!isFormValid) {
      toast("completá las credenciales primero", "warn");
      return;
    }
    if (!confirm("¿hacer backup de la DB operativa al bucket S3?")) return;
    try {
      const r = await backupRun.mutateAsync({ s3: form });
      toast(`backup subido · ${r.key} · ${bytesPretty(r.size_bytes)}`, "success");
      // Refrescamos el listado.
      try {
        await list.mutateAsync({ s3: form });
      } catch {
        // ignore
      }
    } catch (e) {
      toast(`backup falló — ${errMsg(e)}`, "error");
    }
  };

  const onRestore = async (key: string) => {
    if (
      !confirm(
        `¿restaurar "${key}"?\n\nEl backend bajará el archivo como sibling de la DB operativa, pero NO la pisa. Tendrás que apagar el backend, renombrar el sibling y reiniciar para adoptarlo.`,
      )
    )
      return;
    if (!confirm("Confirmá una vez más: esto descarga + descomprime un backup remoto. ¿Seguir?"))
      return;
    try {
      const r = await restore.mutateAsync({ s3: form, key });
      toast(`restore listo · ${r.sibling_path}`, "success");
    } catch (e) {
      toast(`restore falló — ${errMsg(e)}`, "error");
    }
  };

  return (
    <Box
      id={6}
      state={state}
      title="Backup remoto · S3-compatible"
      sub={
        <>
          AWS · Backblaze B2 · Cloudflare R2 · MinIO · respaldo offsite del archivo Config + DB ·
          opcional, no bloquea
        </>
      }
      statusText={statusText}
    >
      <div className="s3-grid">
        <div className="card">
          <div className="card__title">Configuración del bucket</div>
          <div className="card__sub">
            cualquier provider con endpoint URL · multi-region · sin credenciales no se persiste
          </div>

          <div className="s3-fields">
            <div className="field">
              <label htmlFor="s3-endpoint">endpoint URL</label>
              <input
                id="s3-endpoint"
                className="inp"
                type="text"
                value={form.endpoint_url ?? ""}
                onChange={(e) => setForm({ ...form, endpoint_url: e.target.value || null })}
                placeholder="https://s3.amazonaws.com"
              />
            </div>
            <div className="field">
              <label htmlFor="s3-region">region</label>
              <input
                id="s3-region"
                className="inp"
                type="text"
                value={form.region}
                onChange={(e) => setForm({ ...form, region: e.target.value })}
                placeholder="us-east-1"
              />
            </div>
            <div className="field">
              <label htmlFor="s3-bucket">bucket</label>
              <input
                id="s3-bucket"
                className="inp"
                type="text"
                value={form.bucket}
                onChange={(e) => setForm({ ...form, bucket: e.target.value })}
                placeholder="scanner-v5-backups"
              />
            </div>
            <div className="field">
              <label htmlFor="s3-prefix">prefix</label>
              <input
                id="s3-prefix"
                className="inp"
                type="text"
                value={form.key_prefix}
                onChange={(e) => setForm({ ...form, key_prefix: e.target.value })}
                placeholder="scanner-backups/"
              />
            </div>
            <div className="field">
              <label htmlFor="s3-ak">access key</label>
              <input
                id="s3-ak"
                className="inp"
                type="text"
                value={form.access_key_id}
                onChange={(e) => setForm({ ...form, access_key_id: e.target.value })}
                placeholder="AKIAxxx…"
              />
            </div>
            <div className="field">
              <label htmlFor="s3-sk">secret key</label>
              <input
                id="s3-sk"
                className="inp"
                type="password"
                value={form.secret_access_key}
                onChange={(e) => setForm({ ...form, secret_access_key: e.target.value })}
                placeholder="••••••••"
              />
            </div>
          </div>

          <div className="s3-actions">
            <button
              type="button"
              className="btn"
              onClick={onTestConnection}
              disabled={list.isPending || !isFormValid}
            >
              {list.isPending ? "probando…" : "probar conexión"}
            </button>
            <button
              type="button"
              className="btn is-primary"
              onClick={onSaveCreds}
              disabled={putS3.isPending || !isFormValid}
            >
              {putS3.isPending ? "guardando…" : "guardar en .config"}
            </button>
            <button
              type="button"
              className="btn"
              onClick={onBackupNow}
              disabled={backupRun.isPending || !isFormValid}
            >
              {backupRun.isPending ? "subiendo…" : "backup ahora"}
            </button>
          </div>

          <div className="s3-status">
            {list.isPending ? (
              <span style={{ color: "var(--t-55)" }}>— probando —</span>
            ) : list.isError ? (
              <>
                <span className="err">✕</span> probe falló
                <span className="s3-status__hint">
                  verificá endpoint + credenciales · el backup local sigue funcionando · el sistema
                  NO depende de S3
                </span>
              </>
            ) : list.isSuccess ? (
              <>
                <span className="ok">✓</span> conexión OK · {objects.length} backups en el bucket
              </>
            ) : (
              <span style={{ color: "var(--t-55)" }}>— sin probar —</span>
            )}
          </div>
        </div>

        <div className="card">
          <div className="card__title">Backups disponibles</div>
          <div className="card__sub">
            orden descendente por fecha · click <span className="ref">restaurar</span> abre
            confirmación doble
          </div>

          {objects.length === 0 ? (
            <div className="s3-empty" style={{ marginTop: "12px" }}>
              <div className="s3-empty__icon">⊘</div>
              <div className="s3-empty__txt">
                {list.isSuccess ? "no hay backups remotos" : "no hay backups remotos para listar"}
              </div>
              <div className="s3-empty__sub">
                {list.isSuccess
                  ? `bucket ${list.data?.bucket ?? "—"} vacío`
                  : "configurá el bucket en el panel de la izquierda"}
              </div>
            </div>
          ) : (
            <div className="backups-list" style={{ marginTop: "12px" }}>
              <div className="backups-head">key · size · last_modified</div>
              {objects.map((o) => (
                <div key={o.key} className="backup-row">
                  <span className="key">{o.key}</span>
                  <span className="size">{bytesPretty(o.size_bytes)}</span>
                  <span className="ts">{new Date(o.last_modified).toLocaleString()}</span>
                  <span style={{ textAlign: "right" }}>
                    <button
                      type="button"
                      className="btn is-ghost is-danger sm"
                      onClick={() => onRestore(o.key)}
                      disabled={restore.isPending}
                    >
                      restaurar
                    </button>
                  </span>
                </div>
              ))}
            </div>
          )}

          <div className="note" style={{ marginTop: "14px" }}>
            <span className="accent">restaurar</span> siempre crea un sibling de la DB · nunca pisa
            la viva · doble confirmación obligatoria · el backup automático periódico se decide en
            el Dashboard, no acá
          </div>
        </div>
      </div>
    </Box>
  );
}
