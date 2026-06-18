# CONTEXTO PROYECTO CUBOCRAFT
Última actualización: 2026-06-18

## DATOS GENERALES
- Carpeta local: `/home/fernan/cubocraft/`
- GitHub: `github.com/fermounts/cubocraft`
- Web: `https://cubocraft.onrender.com`
- Spreadsheet ID: `1X819OQZwYdu7ldCBYWVxnxBSd7nJAlcGpvjNQw1iSBA`
- Link directo Sheet: `https://docs.google.com/spreadsheets/d/1X819OQZwYdu7ldCBYWVxnxBSd7nJAlcGpvjNQw1iSBA`
- Institución TFI: IFTS N°33 — Tecnicatura Superior en Ciencia de Datos e IA
- Tutora TFI: Marisa Cánovas

## STACK TECNOLÓGICO
- Backend: Flask (Python)
- Base de datos: Google Sheets (via gspread + Service Account)
- Bot WhatsApp: Twilio (recomendación futura: migrar a API oficial Meta)
- IA: Gemini 2.5 Flash (google-generativeai)
- Hosting: Render (web) + UptimeRobot (mantiene Render despierto)

## ARCHIVOS CLAVE EN /home/fernan/cubocraft/
- `webhook_server.py` — servidor Flask principal, recibe mensajes de Twilio
- `bot_handler.py` — lógica del bot, selector CUBO/CRAFT, menú por perfil
- `whatsapp_client.py` — cliente Twilio para enviar mensajes
- `sheets_client.py` — conexión y operaciones con Google Sheets
- `config.py` — variables de configuración
- `session_store.py` — manejo de sesiones de usuario
- `setup_sheets.py` — script para crear/configurar el Sheet desde cero
- `poblar_fichas_tecnicas.py` — script anterior para fichas (chocó con rate limit)
- `completar_sheet.py` — script nuevo (creado 2026-06-06) que reemplaza al anterior
- `credentials.json` — Service Account de Google (copiado de cubocraft-494603-1448c3760a76.json)
- `cubocraft-service-account.json` — archivo original de credenciales (mismo contenido)
- `requirements.txt` — dependencias del proyecto
- `Procfile` — configuración para Render

## ESTADO DEL GOOGLE SHEET

### Nombres reales de hojas (todos en MAYÚSCULAS)
VENDEDORES, PRODUCTOS, PEDIDOS, PAGOS, CAMPAÑAS, RANKING, CANDIDATOS,
CONOCIMIENTO_TECNICO, FICHAS_TECNICAS_BORRADOR, BASE_CONOCIMIENTO, PENDIENTES_VALIDACION

### Hojas con datos reales
- **VENDEDORES** — 3 registros: V001 Fernando (5491134912395), V002 Fernanda (5491134912504), V003 Tomás (5491127104535). Columnas: ID, Nombre, Teléfono, Zona, Perfil, Activa, **Empresa** (AMBAS para los 3)
- **PRODUCTOS** — 80 productos (40 EPP + 40 Materiales de Construcción)
- **PEDIDOS** — 11 pedidos: 3 de Fernando (reales), 4 de Fernanda y 4 de Tomás (prueba, corregidos 2026-06-16)
- **CONOCIMIENTO_TECNICO** — 11 normativas completas
- **BASE_CONOCIMIENTO** — 36 fichas técnicas generadas (44 pendientes por límite Gemini)
- **RANKING** — calculado con datos reales de junio 2026 (actualizado 2026-06-16)

### Hojas completadas 2026-06-06
- **PAGOS** — 5 registros de prueba; columna Anulado eliminada (ver abajo)
- **CAMPAÑAS** — 2 campañas activas cargadas
- **CANDIDATOS** — 3 prospectos de muestra

### RANKING — datos reales junio 2026 (actualizado 2026-06-16)
| Pos | Vendedor | Total mes | Categoría |
|-----|----------|-----------|-----------|
| #1  | Fernando (V001) | $112.837,50 | Oro    |
| #2  | Fernanda (V002) | $68.752,50  | Plata  |
| #3  | Tomás    (V003) | $40.280,00  | Bronce |

El bot muestra el ranking correcto: opción 5 calcula en tiempo real desde PEDIDOS filtrando
por prefijo de producto (EPP→CUBO, MC→CRAFT). Marca "← vos" al vendedor actual.

### BASE_CONOCIMIENTO — EN PROCESO
- 36/80 fichas generadas; se corta por límite diario de Gemini (20 req/día free tier)
- Para retomar: `python3 completar_sheet.py --solo-fichas`
- Checkpoint en: `completar_sheet_progress.json`
- Delay entre requests: 65 segundos; 90 extra si hay rate limit 429

## ESTRUCTURA DE COLUMNAS (definitiva)

### PEDIDOS (12 columnas)
ID_Pedido | Fecha | ID_Vendedor | Nombre_Vendedor | ID_Producto | Nombre_Producto |
Cantidad | Precio_Unit | Descuento_Pct | Total | ID_Campaña | Estado

Estados válidos: PENDIENTE · CANCELADO

⚠️ Los pedidos P20260602135317 y P20260602140406 (los primeros de prueba) tienen columnas
desplazadas por el bug original — Fecha tiene "V001" y ID_Campaña tiene la fecha.
Corregir a mano en el Sheet si se necesitan. (Todos los demás pedidos están correctos.)

### PAGOS (8 columnas — columna Anulado eliminada el 2026-06-06)
ID_Pago | Fecha | ID_Vendedor | Nombre_Vendedor | Monto | Metodo | Comprobante | Estado

Estados válidos: PENDIENTE · CONFIRMADO · ANULADO
El saldo se calcula excluyendo pagos con Estado = ANULADO.

## CAMBIOS EN CÓDIGO (2026-06-06)

### sheets_client.py
- **Bug corregido**: `registrar_pedido()` y `registrar_pago()` tenían Fecha al final
  en lugar de la posición 2 — todos los campos estaban desplazados una columna.
- **`get_saldo()`**: ahora filtra `Estado != "ANULADO"` para no contar pagos anulados.
- **Nuevas funciones**:
  - `get_pedidos_pendientes(vendedor)` — pedidos PENDIENTE del vendedor
  - `cancelar_pedido(id_pedido, id_vendedor)` — cambia Estado a CANCELADO
  - `get_pagos_confirmados_todos()` — todos los pagos CONFIRMADO (para supervisor)
  - `anular_pago(id_pago)` — cambia Estado a ANULADO

### bot_handler.py
- **Nuevos estados**: CANCELAR_PEDIDO, CANCELAR_PEDIDO_CONFIRM, ANULAR_PAGO, ANULAR_PAGO_CONFIRM
- **Comando global vendedor**: "cancelar pedido" → flujo para cancelar pedido PENDIENTE
- **Comando global supervisor**: "anular pago" → flujo para anular pago CONFIRMADO
- En ambos casos se notifica al supervisor por WhatsApp al confirmar.

### Flujo cancelar pedido (vendedor)
```
cancelar pedido → lista de PENDIENTE → número → confirmación SI/NO → CANCELADO
```

### Flujo anular pago (solo supervisor)
```
anular pago → lista de CONFIRMADO → número → confirmación SI/NO → ANULADO
```

## CAMBIOS EN CÓDIGO (2026-06-15)

### Análisis crítico realizado
Se detectaron 18 problemas priorizados. Ver análisis completo en conversación.
Los 3 más críticos fueron corregidos en esta sesión.

### sheets_client.py
- **Fix saldo real**: `registrar_pago()` ahora graba `Estado = "PENDIENTE"` en lugar de
  `"CONFIRMADO"`. El saldo ya no incluye pagos no confirmados.
- **Nuevas funciones**:
  - `get_vendedor_by_id(vid)` — busca vendedor por ID (para notificar al confirmar pago)
  - `get_pagos_pendientes_todos()` — lista de pagos PENDIENTE de todos los vendedores
  - `confirmar_pago(id_pago)` — cambia PENDIENTE → CONFIRMADO
- **Fix BASE_CONOCIMIENTO**: `get_base_conocimiento()` usa `expected_headers` para
  evitar el error por columnas vacías duplicadas (fichas técnicas tienen 12 cols,
  hoja tiene 7 headers definidos).

### bot_handler.py
- **Fix #1 — Saldo real**: opción 3 "Ver mi saldo" ahora usa `get_balance_vendedor()`
  en lugar de `get_saldo()`. Muestra deuda real (pedidos − pagos confirmados) y
  crédito disponible. Informa pagos en revisión si los hay.
- **Fix #2 — Contexto IA**: nueva función `_ficha_a_contexto(r)` detecta si un registro
  de BASE_CONOCIMIENTO es una ficha técnica o una Q&A del pipeline de validación,
  y extrae el contenido útil en ambos casos. Antes el contexto enviado a Gemini
  era vacío para todas las fichas.
- **Fix #3 — Flujo de pagos con confirmación**:
  - Opción 9 (supervisor) ahora abre sub-menú: A=candidatas / B=confirmar-rechazar pagos
  - Nuevos estados: SUPER_MENU, SUPER_CONFIRMAR_PAGO, SUPER_CONFIRMAR_PAGO_CONFIRM
  - Al registrar pago el vendedor ve "enviado para revisión"
  - El supervisor recibe notificación con instrucción para abrir el panel (9 → B)
  - Al confirmar o rechazar se notifica al vendedor por WhatsApp

### Flujo pago (actualizado)
```
vendedor: monto → método → comprobante → SI → graba PENDIENTE → supervisor notificado
supervisor: panel 9 → B → C1/R1 → SI → CONFIRMADO/ANULADO → vendedor notificado
```

### completar_sheet.py (bug corregido 2026-06-15)
- `get_all_records()` fallaba con headers vacíos duplicados en BASE_CONOCIMIENTO.
  Reemplazado por `get_all_values()` con mapeo manual de columnas.
- La lectura del ESTADO también usa los datos en memoria (evita llamadas extra a Sheets API).

### BASE_CONOCIMIENTO — estructura real vs esperada
- Headers reales de la hoja (creados por pipeline Q&A): ID, CATEGORIA, PREGUNTA,
  RESPUESTA_VALIDADA, FUENTE_ORIGINAL, VALIDADO_POR, FECHA_VALIDACION
- Las fichas técnicas generadas por completar_sheet.py se almacenan en esas columnas
  con mapping: nombre→CATEGORIA, apertura→PREGUNTA, DESCRIPCION→RESPUESTA_VALIDADA,
  MODO_USO→FUENTE_ORIGINAL
- `_ficha_a_contexto()` maneja ambos tipos transparentemente

## ESTADO BOT WHATSAPP — OPERATIVO
- Selector CUBO/CRAFT al inicio
- Menú por perfil de usuario
- Pedidos: toma pedido → registra en hoja PEDIDOS del Sheet
- IA con context stuffing: inyecta BASE_CONOCIMIENTO + CONOCIMIENTO_TECNICO completo
- Pipeline validación: PENDIENTES_VALIDACION → BASE_CONOCIMIENTO (job horario)
- Resumen diario al supervisor a las 20hs Argentina
- Cancelación de pedidos y anulación de pagos operativos (2026-06-06)
- Pagos con confirmación del supervisor (2026-06-15): graba PENDIENTE, supervisor confirma desde panel 9→B
- Mensajes "join [keyword]" del sandbox de Twilio ignorados silenciosamente (2026-06-16)
- Logging detallado en webhook: From, Body, estado de sesión, errores con stack trace
- Ranking (opción 5) operativo (2026-06-18): muestra ranking real del mes filtrado por empresa de la sesión

## ESTADO WEB — OPERATIVA
- 3 secciones: Hub central / CUBO / CRAFT
- Carrusel EPP en CUBO (imágenes WebP, 97% menos peso)
- Carrusel CRAFT (mampostería, estructura, durlock)
- Badge UOCRA con efecto animado
- UptimeRobot manteniendo Render despierto

## ESTADO TFI
- Documento actual: CUBOCRAFT_TFI_v5.docx (en carpeta Proyecto Integrador de Drive)
- Correcciones de tutora aplicadas en v5: context stuffing en lugar de RAG
- Pendiente: agregar datos reales de pruebas en secciones 4.2 y 4.5

## CAMBIOS EN CÓDIGO (2026-06-18)

### VENDEDORES — columna Empresa agregada
- Nueva columna G: `Empresa` con valor `AMBAS` para los 3 vendedores existentes.
- `pasar_candidata_a_vendedoras()` ahora incluye `"AMBAS"` al crear vendedores nuevos.
- `get_vendedora_by_phone()` y `get_vendedor_by_id()` devuelven el campo `Empresa` automáticamente.

### sheets_client.py — Ranking reescrito
- Eliminada `get_ranking_vendedora()` (buscaba columna `Período` que no existe).
- Nueva función `calcular_ranking_empresa(empresa)`: calcula ranking en tiempo real desde
  la hoja PEDIDOS, filtrando por prefijo de ID_Producto (EPP→CUBO, MC→CRAFT),
  excluyendo CANCELADOS, filtrando por mes actual.
- Retorna lista ordenada de dicts con Posición, Nombre, Total_Mes, Categoría.

### bot_handler.py — Opción 5 operativa
- Usa `calcular_ranking_empresa(empresa)` con la empresa de la sesión actual.
- Muestra ranking completo del mes con 🥇🥈🥉 y marca "← vos" al vendedor actual.
- Si empresa es CUBO y el vendedor eligió CUBO en esa sesión → ve ranking de EPP.
- Si elige CRAFT → ve ranking de materiales de construcción.

## CAMBIOS EN CÓDIGO (2026-06-16)

### webhook_server.py
- **try/except alrededor de `bot_handler.procesar()` y `enviar()`**: antes una excepción
  devolvía 500 a Twilio que lo interpretaba como fallo silencioso. Ahora siempre devuelve 200.
- **Logging detallado al inicio del webhook**: loguea `From`, `Body`, `NumMedia`, estado de
  sesión, nombre del vendedor y longitud de la respuesta generada.
- **`/debug-config` endpoint**: muestra qué variables de entorno están seteadas en producción
  (sin exponer valores). Útil para diagnosticar Render: `curl https://cubocraft.onrender.com/debug-config`

### bot_handler.py
- **Guard para mensajes "join [keyword]"**: cuando un número nuevo entra al sandbox de Twilio
  manda "join keyword". Antes el bot lo trataba como pregunta libre y llamaba a Gemini.
  Ahora retorna `""` y el webhook no intenta enviar respuesta.
- **Logs adicionales en `procesar()`**: estado, empresa y nombre del vendedor en cada llamada.

### whatsapp_client.py
- **Validación explícita de credenciales**: `_enviar_twilio()` verifica que
  `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN` y `TWILIO_PHONE_NUMBER` estén seteados
  antes de intentar enviar. Antes fallaba silenciosamente con excepción atrapada.

### requirements.txt
- `gspread>=6.2.1` — versión mínima fijada para garantizar soporte de `expected_headers`
  en `get_all_records()`. Sin esto Render podía instalar una versión anterior y fallar.

### PEDIDOS — correcciones de datos (2026-06-16, vía script directo al Sheet)
- 8 fechas de V002 (Fernanda) y V003 (Tomás) normalizadas: `2026-06-XX` → `2026-06-XX 00:00:00`
- `P20260612001` Total: `9562,5` → `9562.5` (coma → punto)

### RANKING — calculado con datos reales junio 2026 (2026-06-16)
- Reemplazó los datos estáticos de prueba por el ranking calculado de los 11 pedidos de junio.
- Calculado con script directo al Sheet (no hay job automático aún).

## PENDIENTES DEL PROYECTO
1. Completar BASE_CONOCIMIENTO (en progreso — `python3 completar_sheet.py --solo-fichas`)
2. Corregir 2 pedidos con columnas desplazadas (P20260602135317, P20260602140406) — a mano en Sheet
3. Probar flujo completo pedido punta a punta
4. Probar flujo pago → supervisor confirma → vendedor notificado
5. ~~Fix ranking en el bot~~ — **RESUELTO 2026-06-18**
6. Sin tabla CLIENTES — no hay registro de a quién vende el vendedor
7. Descuento de campaña se evalúa por item, no por total del carrito (bug de lógica)
8. Fotos reales carrusel CRAFT
9. Imagen corporativa hub central
10. Migrar WhatsApp de Twilio a API oficial Meta (futuro)
11. Agregar datos reales en TFI secciones 4.2 y 4.5

## PROBLEMAS CONOCIDOS — sin corregir aún
- ~~**Ranking en el bot**~~: resuelto 2026-06-18.
- **Descuento**: `aplicar_mejor_descuento()` recibe subtotal de un item, no total del carrito.
- **Baja**: solicitud no toca VENDEDORES, no desactiva al vendedor.
- **Panel supervisor**: sin flujo para validar consultas IA desde el bot.
- **Sin CLIENTES**: pedidos no registran el cliente final.
- **Límite de crédito**: $100,000 hardcodeado, no por vendedor.

## CÓMO USAR ESTE ARCHIVO
Al inicio de cada sesión decile a Claude Code:
leé el CONTEXTO.md y arrancamos desde ahí

Al final de cada sesión decile:
actualizá el CONTEXTO.md con todo lo que hicimos hoy
