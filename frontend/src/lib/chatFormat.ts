/* Texto plano del payload de la señal — formato canon para copiar y pegar
   en chat. Mientras no haya wiring al backend, exporto un fallback con los
   datos hardcoded del Hi-Fi v2 (QQQ A+ CALL 12.0). Cuando llegue el WS,
   `chat_format` viene en el payload del evento `signal.new` y reemplaza
   este fallback. */

export const CHAT_FORMAT_FALLBACK = `═══════════════════════════════════════
SEÑAL · QQQ · A+ · CALL · score 12.0
═══════════════════════════════════════

PRECIO
Último:     $485.32
Chg día:    +0.82%
ATR 15M:    0.74% ($3.59)
dMA200:     +3.2% ($470.12)

CONTEXTO
Alineación: 3/3 CALL  (15M:bull · 1H:bull · D:bull)
MAs diarias: 20=$483 · 40=$478 · 200=$470
BB 1H:      $482.1 / $484.5 / $486.9

VOLUMEN
15M:        1.8× mediana del día
1H:         1.4× mediana del día
Vela curso: 2.1× proyectado (fracción 0.66)
Secuencia:  ↑ creciente

FUERZA RELATIVA
vs SPY:     +0.87%
DivSPY:     QQQ=+0.82% · SPY=+0.41%

NIVELES CLAVE
R: $487.2 (PD) · $489.5 (R1)
S: $483.8 (S1) · $481.1 (PD)

EVENTOS
⚡ Squeeze BB 1H   ancho p12 → expansión
↑ ORB Breakout    rango $484.1-$485.8
⚠️ Catalizador    chg > 1.5×ATR

PATRONES (3)
• [15M] Doji BB inf      bull · trigger · w:2
• [15M] ORB Breakout     bull · trigger · w:2
• [1H]  BBinf_1H         bull · confirm · w:3

SCORING
Estructura: ✓
Triggers:   2 señales  (suma 4.0)
Confirms:   1 señal    (suma 3.0)   tras dedup por categoría
Bloqueo:    —
Conflicto:  —

RESULTADO
Score:      12.0
Dirección:  CALL
Confianza:  A+
Señal:      SETUP

───────────────────────────────────────
Meta
Engine:     5.2.0
Fixture:    qqq_v5_2_0 v5.2.0
Slot:       02
Vela:       2026-04-25 14:30 ET
Cálculo:    2026-04-25 14:30:04 ET`;
