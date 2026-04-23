# Config Module

**Tipo:** módulo de carga/guardado de configuración del usuario con encripción inline.
**Estado:** implementado en modo standalone (cerrado 2026-04-23). Wiring a endpoints pendiente.

## Rol

Maneja el archivo `config_*.json` del usuario. Serializa y deserializa el estado configurable del scanner, con encripción Fernet inline para los 3 campos sensibles: API keys de Twelve Data, credenciales S3, API bearer token del propio scanner.

## Arquitectura

```
modules/config/
├── __init__.py    # API pública
├── crypto.py      # Fernet (AES-128-CBC + HMAC) + resolución de master key
├── models.py      # UserConfig, TDKeyConfig, S3Config (Pydantic frozen)
└── loader.py      # save_config / load_config con atomic write + decrypt en load
```

## API pública

```python
from modules.config import (
    UserConfig, TDKeyConfig, S3Config,  # modelos
    load_config, save_config,            # persistencia
    get_master_key,                      # clave simétrica
    MasterKeyError,                      # errores
)
```

## Master key

Orden de resolución (ver `get_master_key()`):

1. Env var `SCANNER_MASTER_KEY` (base64url, 32 bytes).
2. Archivo en disco `data/master.key` (auto-gen 0600 si no existe).
3. Si `auto_generate=False` y los 2 anteriores fallan → `MasterKeyError`.

## Qué contiene el Config

Schema en `models.UserConfig`:

- `schema_version: str` — semver del modelo (default "1.0.0").
- `name: str` — identificador del Config.
- **Secretos (encriptados):**
  - `twelvedata_keys: list[TDKeyConfig]` — hasta 5 keys con `credits_per_minute`/`credits_per_day`.
  - `s3_config: S3Config | None` — credenciales del backup bucket.
  - `api_bearer_token: str | None` — token del scanner (ADR-0001).
- **No-secretos:**
  - `registry_path: str` — path al `slot_registry.json`.
  - `preferences: dict` — UI, atajos, etc.
  - `auto_last_enabled: bool` — arranque automático desde LAST.

## Operaciones

- `load_config(path, master_key=None)` — lee JSON, desencripta `*_enc`, retorna `UserConfig`.
- `save_config(cfg, path, master_key=None)` — encripta los 3 secretos como `<name>_enc`, escribe JSON con atomic write (tempfile + `os.replace`).

## Invariantes (testeados)

1. Secretos **NO aparecen en cleartext** en el JSON persistido — solo campos `*_enc`.
2. Round-trip `save` → `load` preserva todos los campos bit-a-bit.
3. Key errada al `load` → `MasterKeyError` (no corrupción silenciosa).
4. Atomic write: si `os.replace` falla, el file original queda intacto y no hay tempfiles residuales.

## Pendiente: wiring a endpoints

El Config es standalone. Los endpoints actuales (`POST /database/backup`, etc.) siguen aceptando credenciales en body. La integración se hará cuando el frontend consuma el Config — decisión pendiente: cómo editar desde UI, cuándo recargar, si aplicar cambios en caliente o requerir restart.

## Referencias

- `docs/operational/FEATURE_DECISIONS.md` §3.5 (Fixtures + Config).
- `docs/operational/FEATURE_DECISIONS.md` §4.4 (Persistencia privada).
- `docs/operational/FEATURE_DECISIONS.md` §4.8 (Configuración — archivo JSON).
- `docs/adr/0001-auth-api-bearer-token.md` (bearer token autogenerado).
