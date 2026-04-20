# Scoring Engine

**Tipo:** motor puro (función stateless invocada por otros componentes).
**Estado:** pendiente de implementación.

## Rol

Núcleo del sistema de scoring. Aplica alignment gate + trigger detection + confirm detection con dedup + ORB/conflict check + cálculo de score y franja de confianza.

## Responsabilidades

- Exponer `analyze()` como única función pública del paquete (firma en `SCORING_ENGINE_SPEC.md §2.1`).
- Detectar los 14 patrones de trigger (pesos hardcoded en v5.x.x).
- Detectar las 10 categorías de confirm (pesos leídos desde la fixture).
- Alignment gate + conflict check inline (hardcoded en v5.x.x).
- ORB time gate (≤10:30 ET).
- Asignación de franja según `score_bands` de la fixture.
- Devolver output estructurado sin lanzar excepciones.

## Invariantes (5 del spec, no negociables)

1. **Stateless** — cada llamada es independiente, sin cache interno.
2. **Puro** — sin efectos laterales, sin I/O.
3. **Determinístico** — mismos inputs → mismos outputs bit a bit.
4. **No lanza excepciones** — todos los errores se devuelven como `{"error": True, "error_code": "ENG-XXX"}`.
5. **Fixture read-only** — nunca modifica el dict de fixture recibido.

## Contratos con otros componentes

- **Consume:** velas del Data Engine, fixture del Slot Registry, `sim_datetime` para tests.
- **Provee:** output estructurado al caller (orquestador del ciclo AUTO, Validator, tests de parity).
- **No escribe nada.** La persistencia es responsabilidad del caller.

## Decisiones arquitectónicas relevantes

- Contrato del motor inmutable (ver `docs/specs/SCORING_ENGINE_SPEC.md`).
- `ENG-050` warning cuando el healthcheck detecta divergencia en parity test (ADR relacionado pendiente si aparece).

## Referencias

- `docs/specs/SCORING_ENGINE_SPEC.md` — contrato completo del motor.
- `docs/specs/FIXTURE_SPEC.md` — schema de fixtures que consume.
- `docs/specs/FIXTURE_ERRORS.md` — códigos `ENG-*` que emite.
- `docs/operational/FEATURE_DECISIONS.md` §3.4 (Scoring Engine en el scanner live).
