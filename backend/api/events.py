"""Catálogo de eventos WebSocket (spec §5.3, v1.1.0).

6 eventos oficiales — cada uno con formato de payload estable. El
broadcaster emite envelopes con `{event, timestamp, payload}` donde
`event` es uno de estos strings.

**Frecuencias y uso:**

| Constante              | Frecuencia típica        | Origen                       |
|------------------------|--------------------------|------------------------------|
| EVENT_SIGNAL_NEW       | 1/15min/slot operativo   | Scoring Engine (post-persist) |
| EVENT_SLOT_STATUS      | al cambiar estado        | Slot Registry / Data Engine   |
| EVENT_ENGINE_STATUS    | al cambiar estado        | Motores + supervisor          |
| EVENT_API_USAGE_TICK   | al usarse una API key    | Data Engine (KeyPool)         |
| EVENT_VALIDATOR_PROGRESS | durante corridas       | Validator                     |
| EVENT_SYSTEM_LOG       | eventos puntuales        | Cualquier módulo              |
"""

from __future__ import annotations

EVENT_SIGNAL_NEW: str = "signal.new"
EVENT_SLOT_STATUS: str = "slot.status"
EVENT_ENGINE_STATUS: str = "engine.status"
EVENT_API_USAGE_TICK: str = "api_usage.tick"
EVENT_VALIDATOR_PROGRESS: str = "validator.progress"
EVENT_SYSTEM_LOG: str = "system.log"

ALL_EVENTS: frozenset[str] = frozenset({
    EVENT_SIGNAL_NEW,
    EVENT_SLOT_STATUS,
    EVENT_ENGINE_STATUS,
    EVENT_API_USAGE_TICK,
    EVENT_VALIDATOR_PROGRESS,
    EVENT_SYSTEM_LOG,
})
