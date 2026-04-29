"""Config del usuario en plaintext.

API pública mínima para cargar/guardar el Config del trader:

    from modules.config import (
        UserConfig, TDKeyConfig, S3Config, StartupFlags,
        load_config, save_config,
    )

**Modelo del producto:**

El `.config` es un **archivo portable** que el usuario maneja
explícitamente. El scanner arranca de cero si no se carga ningún
`.config`. Toda la configuración (TD keys, S3, slot assignments,
flags de arranque) vive dentro del archivo. Al apagar el scanner no
queda residuo en el sistema más allá del path "LAST" — solo el
archivo `.config` que el usuario cuida.

**Plaintext por decisión de producto:** el archivo no se encripta. La
seguridad depende de dónde lo guarde el usuario.
"""

from modules.config.loader import load_config, save_config
from modules.config.models import S3Config, StartupFlags, TDKeyConfig, UserConfig

__all__ = [
    "S3Config",
    "StartupFlags",
    "TDKeyConfig",
    "UserConfig",
    "load_config",
    "save_config",
]
