# Scripts auxiliares

Utilidades de mantenimiento del repo. No son parte del runtime del scanner.

## Placeholder

Aún vacío. Candidatos cuando corresponda:

- `scripts/sync_specs_from_observatory.py` — sincronizar specs desde el Observatory (automatizar lo que hoy se hace manual).
- `scripts/build_windows_exe.ps1` — empaquetar el `.exe` con Inno Setup.
- `scripts/generate_parity_reference.py` — regenerar `backend/fixtures/parity_reference/fixtures/parity_qqq_sample.json` (JSON monolítico, 30 sesiones QQQ con seed fijo) contra el Observatory.
- `scripts/rotate_db_manual.py` — disparar rotación de DB desde CLI (utility fuera de la UI del Dashboard).

Cada script debe tener su propio docstring + argparse con `--help` claro.
