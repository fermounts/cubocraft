# CONTEXTO PROYECTO CUBOCRAFT
Última actualización: 2026-06-15

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
- **VENDEDORES** — 1 registro: V001 Fernando
- **PRODUCTOS** — 80 productos (40 EPP + 40 Materiales de Construcción)
- **PEDIDOS** — 2 pedidos de prueba (datos de columnas desplazados — ver nota abajo)
- **CONOCIMIENTO_TECNICO** — 11 normativas completas
- **BASE_CONOCIMIENTO** — fichas técnicas parciales, en proceso de completar

### Hojas completadas 2026-06-06
- **PAGOS** — 5 registros de prueba; columna Anulado eliminada (ver abajo)
- **CAMPAÑAS** — 2 campañas activas cargadas
- **RANKING** — V001 Fernando en posición 1
- **CANDIDATOS** — 3 prospectos de muestra

### BASE_CONOCIMIENTO — EN PROCESO
- 80 fichas técnicas generándose con Gemini 2.5 Flash
- Script corriendo en background: `tail -f /tmp/fichas_loop.log` para monitorear
- Delay entre requests: 65 segundos (free tier Gemini)
- Checkpoint en: `completar_sheet_progress.json`
- Si se interrumpe: `python3 completar_sheet.py --solo-fichas` retoma desde donde quedó

## ESTRUCTURA DE COLUMNAS (definitiva)

### PEDIDOS (12 columnas)
ID_Pedido | Fecha | ID_Vendedor | Nombre_Vendedor | ID_Producto | Nombre_Producto |
Cantidad | Precio_Unit | Descuento_Pct | Total | ID_Campaña | Estado

Estados válidos: PENDIENTE · CANCELADO

⚠️ Los 2 pedidos existentes (P20260602135317, P20260602140406) tienen columnas
desplazadas por el bug original — Fecha tiene "V001" y ID_Campaña tiene la fecha.
Corregir a mano en el Sheet si se necesitan.

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

## PENDIENTES DEL PROYECTO
1. Completar BASE_CONOCIMIENTO (80 fichas — corriendo en background, 26/62 al 2026-06-15)
2. Corregir manualmente los 2 pedidos existentes en el Sheet (columnas desplazadas)
3. Probar flujo completo pedido punta a punta (nuevo código)
4. Probar flujo pago → supervisor confirma → vendedor notificado (nuevo en 2026-06-15)
5. Ranking: triple inconsistencia de headers — nunca devuelve datos (pendiente de fix)
6. Sin tabla CLIENTES — no hay registro de a quién vende el vendedor
7. Descuento de campaña se evalúa por item, no por total del carrito (bug de lógica)
8. Fotos reales carrusel CRAFT
9. Imagen corporativa hub central
10. Migrar WhatsApp de Twilio a API oficial Meta (futuro)
11. Agregar datos reales en TFI secciones 4.2 y 4.5

## PROBLEMAS DETECTADOS (análisis 2026-06-15) — sin corregir aún
- **RANKING** siempre vacío: headers en setup_sheets, sheets_client y display del bot
  son todos distintos. Ningún job calcula el ranking dinámicamente.
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
