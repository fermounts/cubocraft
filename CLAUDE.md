# CUBOCRAFT — Registro de sesiones

## Validación de base de conocimiento — 2026-06-28

Estado final: 73/75 fichas con estado "Aprobado" (las 2 restantes son registros "Q&A legacy" sin estado, no fichas de producto — no requieren acción). Base de conocimiento técnica 100% validada.

Resumen de la sesión:
- Se verificó cada norma IRAM citada en las fichas contra fuentes oficiales (IRAM, CIRSOC, INTI) o fichas técnicas de fabricantes reconocidos (Loma Negra, Knauf, Durlock, Sika, Acindar, Isover, etc.)
- Se detectó un patrón sistemático de normas IRAM inexistentes/inventadas en varias fichas generadas originalmente: IRAM-3632, IRAM-3635, IRAM-3931, IRAM-4241, IRAM-9694, IRAM-1086 (mal aplicada a varios productos), IRAM-1602, IRAM-11605 (mal aplicada). Todas corregidas con la norma real o marcadas como "Sin norma IRAM específica aplicable" cuando no existe norma de producto (ej: masillas, cintas, hidrófugos, pinturas elastoméricas, fieltros asfálticos, barreras de vapor/radiantes).
- Se detectó y corrigió un error propio cometido durante la sesión: perfiles de steel framing (MC-SEC-03/04) se habían aprobado primero con IRAM-IAS U 500-205 (norma de Steel Framing estructural/portante), pero la ficha describe perfiles de drywall no estructural — la norma correcta es IRAM-IAS U 500-243.
- Se implementó (Parte 1 + Parte 2, ya en producción, commit b59dac6 y posteriores) un sistema de detección automática de gaps de conocimiento: cuando Gemini responde "(fuente: no validado por CUBOCRAFT)", el sistema registra la consulta en la hoja GAPS_BASE_CONOCIMIENTO con fecha, vendedor y pregunta original. Con la variable de entorno ENRICH_GAPS=true (desactivada por defecto para no consumir cuota en demos), una segunda llamada a Gemini clasifica además categoría, atributo solicitado y nivel de confianza.
- Se agregó al system prompt de Gemini (bot_handler.py, procesar_consulta_ia()) una instrucción para rechazar preguntas fuera del dominio (seguridad industrial / sistemas constructivos) y para advertir explícitamente cuando un producto consultado no está validado en el catálogo, evitando alucinaciones de conocimiento general sin aclarar la fuente.

Pendiente para después de la defensa (no urgente): ninguna ficha queda en Borrador, pero quedó identificado que el flujo "Parte 2" de estructuración de gaps no crea automáticamente una ficha técnica nueva — ese paso de formalización sigue siendo manual.
