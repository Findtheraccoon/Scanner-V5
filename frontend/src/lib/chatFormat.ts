/* Fallback para el botón COPIAR cuando NO hay signal cargada (slot vacío,
   backend offline, etc.).

   BUG-024: antes este archivo contenía un fallback hardcoded del Hi-Fi v2
   con `$485.32` etc. — cuando la signal venía sin `chat_format` (caso real:
   /signals/latest leídos de DB no traen chat_format, solo el WS event lo
   incluía), el COPIAR pegaba esos valores fake al portapapeles. Ahora el
   backend genera chat_format en read time vía `_augment_signal`, y este
   fallback es solo un mensaje claro de "no hay datos". */

export const CHAT_FORMAT_FALLBACK = `═══════════════════════════════════════
SIN SEÑAL CARGADA
═══════════════════════════════════════

No hay señal disponible para copiar todavía.
Dispará un scan desde el botón "SCAN AHORA" del Cockpit
o esperá al próximo ciclo del auto-scan.`;
