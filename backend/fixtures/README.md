# Fixtures embebidos

**Estado:** pendiente de poblado inicial (`qqq_canonical_v1` + sibling `.metrics.json` al mínimo).

## Qué vive acá

Los **canonicals** aprobados del Observatory, embebidos en el release del scanner. Son archivos inmutables con hash SHA-256.

Layout esperado:

```
fixtures/
├── qqq_canonical_v1.json            # Canonical de QQQ (inmutable)
├── qqq_canonical_v1.sha256          # Hash de control
├── qqq_canonical_v1.metrics.json    # Sibling con métricas de calibración
├── qqq_canonical_v2.json            # Múltiples canonicals coexisten (desvío #5)
├── ...
└── parity_reference/
    ├── README.md                        # Fuente de verdad del sample (formato + ventana)
    ├── parity_qqq_canonical.py          # Script go/no-go del parity check
    └── fixtures/parity_qqq_sample.json  # Dataset de 30 sesiones QQQ 2025 (245 señales)
```

## Qué NO vive acá

- **Fixtures activas del trader** — esas viven dentro del archivo Config del usuario, no en este directorio (desvío #7 de `FEATURE_DECISIONS`).
- **DBs** — esas viven en `data/` (gitignored).
- **Configs** — esas las maneja el trader (`config_*.json`).

## Reglas

1. Los canonicals son **inmutables**. Si hay que cambiar algo, se genera `qqq_canonical_v2.json` con nuevo hash, el v1 permanece.
2. Al arrancar, el sistema verifica el hash de cada canonical referenciado por fixtures activas. Mismatch → `REG-020` fatal.
3. Múltiples canonicals por ticker **coexisten** (para A/B silencioso entre canonicals aprobados).
4. El sibling `.metrics.json` es **obligatorio** para canonicals con `status: final`, opcional para activas (ver `METRICS_FILE_SPEC.md`).

## Dataset de parity

`parity_reference/` contiene el dataset concreto que el Validator usa para su test F. Formato: JSON monolítico (`parity_qqq_sample.json` con metadata + array `signals`). Ventana: 30 sesiones de QQQ en 2025 (2-3 por mes, seed fijo=42), 245 señales cubriendo las 6 franjas. El `README.md` interno del directorio es la fuente de verdad del sample.

## Referencias

- `docs/specs/FIXTURE_SPEC.md` — schema de fixtures.
- `docs/specs/METRICS_FILE_SPEC.md` — schema del sibling.
- `docs/specs/CANONICAL_MANAGER_SPEC.md` — proceso de aprobación (vive en Observatory).
- `docs/operational/FEATURE_DECISIONS.md` §3.5 (Fixtures en scanner live).
