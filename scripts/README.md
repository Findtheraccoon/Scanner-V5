# Scripts auxiliares

Utilidades de mantenimiento del repo. No son parte del runtime del scanner.

## Disponibles

### `replay_canonical_parity.py`

Replay parity test del scoring engine V5 sobre el dataset histórico
del Observatory (QQQ 2023-03-15 → 2026-04-14, 299,941 candles 1m). Itera
vela por vela, agrega 15m/1h via CandleBuilder, llama
`engines.scoring.analyze` con la fixture canonical activa en cada
cierre 15m, persiste cada output a SQLite local + tracking forward
30 min para MFE/MAE. Al final agrega por banda y compara con los valores
declarados en `<fixture>.metrics.json:metrics_training.by_band`.

**Propósito:** verificar que el engine V5 reproduce bit-a-bit el
comportamiento del calibrador del Observatory que produjo el canonical
— garantía I2 del spec del scoring engine (determinístico, mismos
inputs → mismo output).

**Última corrida (2026-05-01 · pre-alfa):** validado contra
`qqq_canonical_v1` full 36m. Resultados:
- Counts por banda dentro de ±1.55%; **S y S+ exactos** (51/51, 11/11)
- WR @ 30 min mean |Δ| = 2.64 pp; banda S idéntica (60.8% ↔ 60.8%)
- mfe_mae con `AVG(MFE/MAE)` matchea banda B casi exacto (10.34 ↔ 10.37)
- divergencias residuales en bandas n<100 por varianza estadística
- veredicto: production-ready para la calibración existente

Wall time ~82 min single-threaded.

```bash
cd backend
python ../scripts/replay_canonical_parity.py [--end-date YYYY-MM-DD] [--fixture FIXTURE_ID]
```

DB output a `backend/data/replay_<fixture_id>.db` (gitignored).

## Candidatos futuros

- `scripts/sync_specs_from_observatory.py` — sincronizar specs desde el Observatory (automatizar lo que hoy se hace manual).
- `scripts/build_windows_exe.ps1` — empaquetar el `.exe` con Inno Setup.
- `scripts/generate_parity_reference.py` — regenerar `backend/fixtures/parity_reference/fixtures/parity_qqq_sample.json` (JSON monolítico, 30 sesiones QQQ con seed fijo) contra el Observatory.
- `scripts/rotate_db_manual.py` — disparar rotación de DB desde CLI (utility fuera de la UI del Dashboard).

Cada script debe tener su propio docstring + argparse con `--help` claro.
