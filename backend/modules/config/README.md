# Config Module

**Tipo:** módulo de carga/guardado del Config del usuario.
**Estado:** plaintext, wired a `/api/v1/config/*` (Capa Frontend → Configuración).

## Rol

Maneja el archivo `.config` del usuario. Serializa y deserializa el estado
configurable del scanner como JSON plaintext.

**Modelo del producto:** el `.config` es un documento portable que el usuario
maneja con Cargar / Guardar / LAST. El sistema no persiste secretos por su
cuenta — si no se carga ningún `.config`, el scanner arranca de cero.

## Arquitectura

```
modules/config/
├── __init__.py    # API pública
├── models.py      # UserConfig, TDKeyConfig, S3Config, StartupFlags (Pydantic frozen)
└── loader.py      # save_config / load_config con atomic write
```

## API pública

```python
from modules.config import (
    UserConfig, TDKeyConfig, S3Config, StartupFlags,  # modelos
    load_config, save_config,                          # persistencia
)
```

## Qué contiene el Config

Schema en `models.UserConfig`:

- `schema_version: str` — semver del modelo (default "1.0.0").
- `name: str` — identificador del Config.
- `twelvedata_keys: list[TDKeyConfig]` — hasta 5 keys con `credits_per_minute`/`credits_per_day`.
- `s3_config: S3Config | None` — credenciales del backup bucket.
- `api_bearer_token: str | None` — token del scanner (ADR-0001).
- `registry_path: str` — path al `slot_registry.json`.
- `preferences: dict` — UI, atajos, etc.
- `auto_last_enabled: bool` — arranque automático desde LAST.
- `startup_flags: StartupFlags` — overrides de `Settings` cuando hay `.config` cargado.

## Operaciones

- `load_config(path)` — lee JSON plaintext, retorna `UserConfig`.
- `save_config(cfg, path)` — escribe JSON con atomic write (tempfile + `os.replace`).

## Invariantes (testeados)

1. Round-trip `save` → `load` preserva todos los campos bit-a-bit.
2. Atomic write: si `os.replace` falla, el archivo original queda intacto y
   no hay tempfiles residuales.
3. Schema rechaza campos extra desconocidos (`extra="forbid"`).

## Endpoints REST asociados

`backend/api/routes/config.py` expone:

- `POST /api/v1/config/load` — carga `.config` del path al runtime.
- `POST /api/v1/config/save` — guarda runtime al path actual (o body).
- `POST /api/v1/config/save_as` — guarda runtime al path nuevo.
- `GET /api/v1/config/last` — retorna el path del último `.config` cargado.
- `GET /api/v1/config/current` — retorna el `UserConfig` runtime.
- `POST /api/v1/config/clear` — wipe del runtime.
- `PUT /api/v1/config/twelvedata_keys` — edita keys en runtime + reload del KeyPool.
- `PUT /api/v1/config/s3` — edita S3 en runtime.
- `PUT /api/v1/config/startup_flags` — edita flags en runtime.
- `POST /api/v1/config/reload-policies` — hot-reload del watchdog.

## Referencias

- `frontend/wireframing/Configuracion specs.md` — spec funcional Pasos 1-5.
- `docs/operational/FEATURE_DECISIONS.md` §3.5 / §4.8.
- `docs/adr/0001-auth-api-bearer-token.md` (bearer token autogenerado).
