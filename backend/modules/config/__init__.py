"""Config del usuario con encripción inline de secretos.

API pública mínima para cargar/guardar el Config del trader:

    from modules.config import (
        UserConfig, TDKeyConfig, S3Config,
        load_config, save_config,
        get_master_key,
    )

**Flujo típico (post integración al frontend):**

    # Al arranque del backend:
    cfg = load_config("data/config_last.json")

    # Al editar desde el frontend:
    new_cfg = cfg.model_copy(update={"twelvedata_keys": new_keys})
    save_config(new_cfg, "data/config_last.json")

**Estado actual (módulo standalone, sin wiring al backend):**

El Config existe pero no está integrado aún a los endpoints. Los
endpoints de backup/restore S3 siguen aceptando credenciales en body
por compat. La integración se hará cuando el frontend exista y
consuma el Config (decisión documentada como deuda técnica en AR.2).
"""

from modules.config.crypto import (
    MasterKeyError,
    decrypt_str,
    encrypt_str,
    get_master_key,
)
from modules.config.loader import load_config, save_config
from modules.config.models import S3Config, TDKeyConfig, UserConfig

__all__ = [
    "MasterKeyError",
    "S3Config",
    "TDKeyConfig",
    "UserConfig",
    "decrypt_str",
    "encrypt_str",
    "get_master_key",
    "load_config",
    "save_config",
]
