"""Database Engine — supervisor de la DB.

Motor separado del módulo `modules.db` (capa de acceso puro). Este
engine es el **supervisor**:

- Emite heartbeats periódicos con el estado de cada motor.
- Corre rotación de datos vencidos (`signals`, `heartbeat`, `system_log`)
  según políticas de retención.
- Orquestra backups locales (y, en una fase siguiente, upload a S3).

**Separación:** `modules.db` es una **biblioteca de funciones**
(write_signal, read_*, etc.). `engines.database` es el **proceso/motor**
que las usa para mantener la DB saludable.
"""

from engines.database.heartbeat import emit_engine_heartbeat
from engines.database.rotation import DEFAULT_RETENTION_POLICIES, rotate_expired

__all__ = [
    "DEFAULT_RETENTION_POLICIES",
    "emit_engine_heartbeat",
    "rotate_expired",
]
