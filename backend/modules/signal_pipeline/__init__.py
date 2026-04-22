"""Pipeline de señales — orquesta `analyze()` + persist + broadcast.

Expone `scan_and_emit()` como función pura pero efectual: corre el
motor puro stateless, persiste el resultado en la DB y (si corresponde)
broadcast `signal.new` al WebSocket. El motor `engines.scoring` sigue
sin estado ni efectos — esta capa es la responsable de los side effects.
"""

from modules.signal_pipeline.pipeline import (
    build_chat_format,
    build_ws_payload,
    scan_and_emit,
)

__all__ = ["build_chat_format", "build_ws_payload", "scan_and_emit"]
